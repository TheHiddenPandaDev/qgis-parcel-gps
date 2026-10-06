from __future__ import annotations

import html
import os

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeatureRequest,
    QgsMapLayerProxyModel,
    QgsMessageLog,
    QgsProject,
    QgsVectorFileWriter,
)
from qgis.gui import QgsFieldComboBox, QgsMapLayerComboBox, QgsMapToolEmitPoint
from qgis.PyQt.QtCore import QLocale, Qt
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .core.batch import BatchJob, BatchSummary, build_jobs, clean_reference
from .core.client import DEVELOPER_PORTAL_URL
from .core.countries import COUNTRY_CODES, PUBLIC_COUNTRY_COUNT, country_label, normalize_country
from .basemap import (
    BASEMAP_MARKER,
    CADASTRE_MARKER,
    add_cadastre_overlay,
    ensure_basemap,
    framed_extent,
    owned_layer,
    remove_cadastre_overlay,
    replace_basemap,
    use_web_mercator,
)
from .core.errors import AmbiguousReferenceError
from .core.presentation import (
    BASEMAP_NONE,
    BASEMAP_SATELLITE,
    BASEMAP_STREETS,
    basemap_for,
    detail_rows,
    offers_cadastre_overlay,
)
from .fetch_task import FetchTask
from .i18n import tr
from .results_layer import add_records, find_results_layer
from .settings_store import load_api_key, load_basemap, load_country, save_api_key, save_basemap, save_country

LOG_TAG = "Parcel GPS"
WGS84 = "EPSG:4326"
CONFIRM_BATCH_ABOVE = 25
MAX_LISTED_FAILURES = 5
MUTED_COLOR = "#64748b"
SAVE_DRIVERS = {
    ".gpkg": "GPKG",
    ".geojson": "GeoJSON",
    ".json": "GeoJSON",
    ".shp": "ESRI Shapefile",
    ".kml": "KML",
}


def _link(text: str) -> str:
    return f'<a href="{DEVELOPER_PORTAL_URL}">{text}</a>'


def error_message(error: Exception) -> str:
    kind = getattr(error, "kind", "generic")
    portal = _link("parcelgps.com/developers")
    messages = {
        "auth": tr("The API key was rejected. Check it, or get a free key (250 requests a month) at {link}."),
        "forbidden": tr("This API key is not allowed to use this service. Check your plan at {link}."),
        "quota": tr("Your monthly quota is used up. Upgrade your plan or add prepaid balance at {link}."),
        "rate_limit": tr("Too many requests per minute. Wait a moment and try again."),
        "coverage": tr(
            "This reference belongs to a country without coverage. Parcel GPS covers {count} European countries."
        ),
        "place_name": tr("That looks like a place name, not a cadastral reference."),
        "not_found": tr("No cadastral parcel was found."),
        "no_outline": tr("The parcel was found, but the API returned no outline for it."),
        "validation": tr("The request was not valid: {detail}"),
        "timeout": tr("The Parcel GPS API did not answer in time. Try again."),
        "network": tr("Could not reach the Parcel GPS API. Check your connection or proxy settings."),
        "server": tr("The Parcel GPS service had a problem. Try again in a few minutes."),
        "unavailable": tr("The official cadastre is not answering right now. Try again in a few minutes."),
    }
    if isinstance(error, AmbiguousReferenceError):
        countries = ", ".join(country_label(code) for code in error.candidate_countries) or "?"
        return tr(
            "This reference could belong to several countries ({countries}). Choose the country and try again."
        ).format(countries=countries)
    template = messages.get(kind)
    detail = html.escape(str(getattr(error, "message", error)))
    if template is None:
        return tr("Unexpected error: {detail}").format(detail=detail)
    return template.format(link=portal, count=PUBLIC_COUNTRY_COUNT, detail=detail)


class ParcelGpsDock(QDockWidget):
    def __init__(self, iface, parent: QWidget | None = None) -> None:
        super().__init__(tr("Parcel GPS"), parent)
        self.setObjectName("ParcelGpsDock")
        self._iface = iface
        self._task: FetchTask | None = None
        self._map_tool = QgsMapToolEmitPoint(iface.mapCanvas())
        self._map_tool.canvasClicked.connect(self._on_map_clicked)
        self._map_tool.deactivated.connect(lambda: self.pick_button.setChecked(False))
        self._build()
        self._restore()

    def shutdown(self) -> None:
        if self._task is not None:
            self._task.cancel()
        canvas = self._iface.mapCanvas()
        if canvas.mapTool() is self._map_tool:
            canvas.unsetMapTool(self._map_tool)

    def _build(self) -> None:
        body = QWidget(self)
        layout = QVBoxLayout(body)
        layout.addWidget(self._build_key_box())
        layout.addWidget(self._build_search_box())
        layout.addWidget(self._build_batch_box())
        layout.addWidget(self._build_map_box())
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        self.status_label = self._rich_label()
        self.details_label = self._rich_label()
        self.details_label.setVisible(False)
        self.quota_label = self._rich_label()
        self.source_label = self._rich_label()
        for label in (self.status_label, self.details_label, self.quota_label, self.source_label):
            layout.addWidget(label)
        layout.addLayout(self._build_result_buttons())
        footer = self._rich_label(
            tr("Official cadastral parcels of {count} European countries through the {link} API.").format(
                count=PUBLIC_COUNTRY_COUNT, link=_link("Parcel GPS")
            )
        )
        footer.setStyleSheet("color: palette(mid);")
        layout.addWidget(footer)
        layout.addStretch(1)
        self.setWidget(body)

    def _build_key_box(self) -> QGroupBox:
        box = QGroupBox(tr("API key"))
        layout = QVBoxLayout(box)
        row = QHBoxLayout()
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText(tr("Paste your Parcel GPS API key"))
        save = QPushButton(tr("Save"))
        save.clicked.connect(self._save_key)
        row.addWidget(self.key_edit, 1)
        row.addWidget(save)
        layout.addLayout(row)
        layout.addWidget(self._rich_label(_link(tr("Get a free API key (250 requests a month)"))))
        return box

    def _build_search_box(self) -> QGroupBox:
        box = QGroupBox(tr("Find a parcel"))
        form = QFormLayout(box)
        self.country_combo = QComboBox()
        self.country_combo.addItem(tr("Detect automatically"), "")
        for code in COUNTRY_CODES:
            self.country_combo.addItem(f"{country_label(code)} ({code})", code)
        self.country_combo.currentIndexChanged.connect(lambda _index: save_country(self._country() or ""))
        form.addRow(tr("Country"), self.country_combo)
        row = QHBoxLayout()
        self.reference_edit = QLineEdit()
        self.reference_edit.setPlaceholderText(tr("Cadastral reference, e.g. 9872023VH5797S0001WX"))
        self.reference_edit.returnPressed.connect(self._fetch_reference)
        self.fetch_button = QPushButton(tr("Fetch"))
        self.fetch_button.clicked.connect(self._fetch_reference)
        row.addWidget(self.reference_edit, 1)
        row.addWidget(self.fetch_button)
        form.addRow(tr("Reference"), row)
        self.pick_button = QPushButton(tr("Pick a parcel on the map"))
        self.pick_button.setCheckable(True)
        self.pick_button.toggled.connect(self._toggle_map_tool)
        form.addRow(self.pick_button)
        return box

    def _build_batch_box(self) -> QGroupBox:
        box = QGroupBox(tr("Batch from a table"))
        form = QFormLayout(box)
        self.layer_combo = QgsMapLayerComboBox()
        self.layer_combo.setFilters(QgsMapLayerProxyModel.Filter.VectorLayer)
        self.reference_field = QgsFieldComboBox()
        self.country_field = QgsFieldComboBox()
        self.country_field.setAllowEmptyFieldName(True)
        self.layer_combo.layerChanged.connect(self._on_layer_changed)
        self._on_layer_changed(self.layer_combo.currentLayer())
        self.selected_only = QCheckBox(tr("Selected features only"))
        form.addRow(tr("Layer"), self.layer_combo)
        form.addRow(tr("Reference field"), self.reference_field)
        form.addRow(tr("Country field (optional)"), self.country_field)
        form.addRow(self.selected_only)
        row = QHBoxLayout()
        self.batch_button = QPushButton(tr("Fetch all"))
        self.batch_button.clicked.connect(self._fetch_batch)
        self.cancel_button = QPushButton(tr("Cancel"))
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel)
        row.addWidget(self.batch_button, 1)
        row.addWidget(self.cancel_button)
        form.addRow(row)
        return box

    def _build_map_box(self) -> QGroupBox:
        box = QGroupBox(tr("Map"))
        form = QFormLayout(box)
        self.basemap_combo = QComboBox()
        self.basemap_combo.addItem(tr("Satellite (Esri)"), BASEMAP_SATELLITE)
        self.basemap_combo.addItem(tr("Street map (OpenStreetMap)"), BASEMAP_STREETS)
        self.basemap_combo.addItem(tr("None"), BASEMAP_NONE)
        form.addRow(tr("Basemap"), self.basemap_combo)
        self.attribution_label = self._rich_label()
        self.attribution_label.setStyleSheet(f"color: {MUTED_COLOR};")
        form.addRow(self.attribution_label)
        self.cadastre_check = QCheckBox(tr("Show official cadastre layer"))
        self.cadastre_check.setVisible(False)
        self.cadastre_check.toggled.connect(self._toggle_cadastre)
        form.addRow(self.cadastre_check)
        return box

    def _build_result_buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()
        zoom = QPushButton(tr("Zoom to results"))
        zoom.clicked.connect(self._zoom_to_layer)
        save = QPushButton(tr("Save results..."))
        save.clicked.connect(self._save_results)
        row.addWidget(zoom)
        row.addWidget(save)
        return row

    def _rich_label(self, text: str = "") -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setOpenExternalLinks(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        return label

    def _restore(self) -> None:
        self.key_edit.setText(load_api_key())
        index = self.country_combo.findData(load_country())
        self.country_combo.setCurrentIndex(max(index, 0))
        self.basemap_combo.setCurrentIndex(max(self.basemap_combo.findData(load_basemap()), 0))
        self._show_attribution()
        self.basemap_combo.currentIndexChanged.connect(self._on_basemap_changed)

    def _country(self) -> str | None:
        return normalize_country(self.country_combo.currentData())

    def _api_key(self) -> str | None:
        key = self.key_edit.text().strip()
        if key:
            return key
        self._show_status(
            tr("Paste an API key first. You can get a free one at {link}.").format(
                link=_link("parcelgps.com/developers")
            ),
            error=True,
        )
        return None

    def _save_key(self) -> None:
        save_api_key(self.key_edit.text())
        self._show_status(tr("API key saved.") if self.key_edit.text().strip() else tr("API key removed."))

    def _on_layer_changed(self, layer) -> None:
        self.reference_field.setLayer(layer)
        self.country_field.setLayer(layer)
        self.country_field.setField("")

    def _toggle_map_tool(self, checked: bool) -> None:
        canvas = self._iface.mapCanvas()
        if checked:
            canvas.setMapTool(self._map_tool)
            self._show_status(tr("Click on the map to fetch the parcel at that point."))
        elif canvas.mapTool() is self._map_tool:
            canvas.unsetMapTool(self._map_tool)

    def _on_map_clicked(self, point, _button) -> None:
        if self._busy():
            return
        canvas = self._iface.mapCanvas()
        transform = QgsCoordinateTransform(
            canvas.mapSettings().destinationCrs(), QgsCoordinateReferenceSystem(WGS84), QgsProject.instance()
        )
        wgs84 = transform.transform(point)
        self._start(
            tr("Parcel GPS: parcel at a point"),
            [BatchJob(f"{wgs84.y():.6f}, {wgs84.x():.6f}", self._country())],
            point=(wgs84.y(), wgs84.x()),
        )

    def _fetch_reference(self) -> None:
        reference = clean_reference(self.reference_edit.text())
        if not reference:
            self._show_status(tr("Type a cadastral reference first."), error=True)
            return
        self._start(tr("Parcel GPS: {reference}").format(reference=reference), [BatchJob(reference, self._country())])

    def _fetch_batch(self) -> None:
        layer = self.layer_combo.currentLayer()
        reference_field = self.reference_field.currentField()
        if layer is None or not reference_field:
            self._show_status(tr("Choose a layer and the field that holds the references."), error=True)
            return
        jobs = build_jobs(self._rows(layer, reference_field, self.country_field.currentField()), self._country())
        if not jobs:
            self._show_status(tr("No references found in that field."), error=True)
            return
        if len(jobs) > CONFIRM_BATCH_ABOVE and not self._confirm_batch(len(jobs)):
            return
        self._start(tr("Parcel GPS: {count} references").format(count=len(jobs)), jobs)

    def _rows(self, layer, reference_field: str, country_field: str):
        request = QgsFeatureRequest()
        request.setFlags(QgsFeatureRequest.Flag.NoGeometry)
        features = layer.getSelectedFeatures(request) if self.selected_only.isChecked() else layer.getFeatures(request)
        for feature in features:
            country = _plain(feature[country_field]) if country_field else None
            yield _plain(feature[reference_field]), country

    def _confirm_batch(self, count: int) -> bool:
        answer = QMessageBox.question(
            self,
            tr("Parcel GPS"),
            tr("Fetch {count} references? Each one uses at least one request of your monthly quota.").format(
                count=count
            ),
        )
        return answer == QMessageBox.StandardButton.Yes

    def _busy(self) -> bool:
        if self._task is None:
            return False
        self._show_status(tr("A request is already running."), error=True)
        return True

    def _start(self, description: str, jobs: list, point=None) -> None:
        api_key = self._api_key()
        if api_key is None or self._busy():
            return
        task = FetchTask(description, api_key, jobs, point=point)
        task.outcome_ready.connect(self._on_outcome)
        task.done.connect(self._on_done)
        task.progressChanged.connect(lambda value: self.progress.setValue(int(value)))
        self._task = task
        self._set_running(True, batch=len(jobs) > 1)
        self._show_status(tr("Fetching..."))
        QgsApplication.taskManager().addTask(task)

    def _set_running(self, running: bool, batch: bool = False) -> None:
        self.fetch_button.setEnabled(not running)
        self.batch_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.progress.setVisible(running and batch)
        self.progress.setValue(0)

    def _cancel(self) -> None:
        if self._task is not None:
            self._task.cancel()

    def _on_outcome(self, outcome) -> None:
        if outcome.record is not None:
            project = QgsProject.instance()
            existing = find_results_layer(project)
            first = existing is None or existing.featureCount() == 0
            _, extent, _, measured = add_records(project, [outcome.record])
            if first:
                self._prepare_map(project)
            self.source_label.setText(tr("Source: {source}").format(source=html.escape(outcome.record.source_text())))
            if self._task is not None and self._task.job_count == 1:
                self._show_details(measured[0] if measured else outcome.record)
                if not extent.isEmpty():
                    self._zoom_to(extent)
            return
        job, error = outcome.job, outcome.error
        QgsMessageLog.logMessage(
            f"{job.reference} ({job.country or 'auto'}): {error.kind} - {error.message}",
            LOG_TAG,
            Qgis.MessageLevel.Warning,
        )

    def _on_done(self, task: FetchTask) -> None:
        self._task = None
        self._set_running(False)
        self._show_quota(task.quota)
        if task.error is not None:
            self._show_status(error_message(task.error), error=True)
            return
        summary = task.summary or BatchSummary()
        if summary.total == 1 and summary.failures:
            self._show_status(error_message(summary.failures[0].error), error=True)
        elif summary.total == 1 and summary.fetched == 1:
            self._show_status(tr('Parcel added to the "Parcel GPS" layer.'))
        else:
            self._show_batch_summary(summary)

    def _show_batch_summary(self, summary: BatchSummary) -> None:
        lines = [
            tr("Fetched {fetched} of {total} parcels; {failed} failed.").format(
                fetched=summary.fetched, total=summary.total, failed=summary.failed
            )
        ]
        if summary.cancelled:
            lines.append(tr("Cancelled: {count} references were not processed.").format(count=summary.not_processed))
        if summary.stopped_by is not None:
            lines.append(error_message(summary.stopped_by))
        for failure in summary.failures[:MAX_LISTED_FAILURES]:
            lines.append(f"{html.escape(failure.job.reference)}: {error_message(failure.error)}")
        if len(summary.failures) > MAX_LISTED_FAILURES:
            lines.append(tr("All failures are listed in the Parcel GPS tab of the log panel."))
        self._show_status("<br>".join(lines), error=bool(summary.failed or summary.stopped_by))
        level = Qgis.MessageLevel.Warning if summary.failed else Qgis.MessageLevel.Success
        self._iface.messageBar().pushMessage(
            tr("Parcel GPS"),
            tr("Fetched {fetched} of {total} parcels.").format(fetched=summary.fetched, total=summary.total),
            level=level,
            duration=6,
        )

    def _show_quota(self, quota: dict | None) -> None:
        if not quota or "remaining" not in quota:
            return
        text = tr("Quota: {remaining} requests left this month").format(remaining=quota["remaining"])
        if "limit" in quota:
            text = tr("Quota: {remaining} of {limit} requests left this month").format(
                remaining=quota["remaining"], limit=quota["limit"]
            )
        if quota.get("plan"):
            text = f"{text} ({quota['plan']})"
        self.quota_label.setText(text)

    def _show_status(self, text: str, error: bool = False) -> None:
        self.status_label.setStyleSheet("color: #b71c1c;" if error else "")
        self.status_label.setText(text)

    def _zoom_to(self, extent) -> None:
        canvas = self._iface.mapCanvas()
        canvas.setExtent(framed_extent(QgsProject.instance(), extent, canvas.mapSettings().destinationCrs()))
        canvas.refresh()

    def _prepare_map(self, project: QgsProject) -> None:
        if ensure_basemap(project, self._basemap_choice()) is not None:
            use_web_mercator(project, self._iface.mapCanvas())

    def _basemap_choice(self) -> str:
        return self.basemap_combo.currentData() or BASEMAP_SATELLITE

    def _show_attribution(self) -> None:
        basemap = basemap_for(self._basemap_choice())
        text = tr("Basemap: {attribution}").format(attribution=html.escape(basemap.attribution)) if basemap else ""
        self.attribution_label.setText(text)
        self.attribution_label.setVisible(bool(text))

    def _on_basemap_changed(self, _index: int) -> None:
        choice = self._basemap_choice()
        save_basemap(choice)
        self._show_attribution()
        project = QgsProject.instance()
        layer = find_results_layer(project)
        had_owned = owned_layer(project, BASEMAP_MARKER) is not None
        if layer is None or (layer.featureCount() == 0 and not had_owned):
            return
        if replace_basemap(project, choice) is not None:
            use_web_mercator(project, self._iface.mapCanvas())
        self._iface.mapCanvas().refresh()

    def _toggle_cadastre(self, checked: bool) -> None:
        project = QgsProject.instance()
        if not checked:
            remove_cadastre_overlay(project)
            return
        if add_cadastre_overlay(project, find_results_layer(project)) is None:
            self.cadastre_check.blockSignals(True)
            self.cadastre_check.setChecked(False)
            self.cadastre_check.blockSignals(False)
            self._show_status(tr("The official cadastre map of Spain is not answering right now."), error=True)

    def _show_details(self, record) -> None:
        names = {
            "reference": tr("Reference"),
            "municipality": tr("Municipality"),
            "area": tr("Area"),
            "centroid": tr("Centroid"),
        }
        rows = "".join(
            f'<tr><td style="color: {MUTED_COLOR}; padding-right: 8px;">{html.escape(names[key])}</td>'
            f"<td><b>{html.escape(value)}</b></td></tr>"
            for key, value in detail_rows(record, str(QLocale().decimalPoint()))
        )
        self.details_label.setText(f'<table cellspacing="0" cellpadding="1">{rows}</table>')
        self.details_label.setVisible(True)
        overlay = owned_layer(QgsProject.instance(), CADASTRE_MARKER) is not None
        self.cadastre_check.setVisible(offers_cadastre_overlay(record.country) or overlay)

    def _zoom_to_layer(self) -> None:
        layer = find_results_layer(QgsProject.instance())
        if layer is None or layer.featureCount() == 0:
            self._show_status(tr("There are no results yet."), error=True)
            return
        layer.updateExtents()
        self._zoom_to(layer.extent())

    def _save_results(self) -> None:
        layer = find_results_layer(QgsProject.instance())
        if layer is None or layer.featureCount() == 0:
            self._show_status(tr("There are no results yet."), error=True)
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("Save Parcel GPS results"),
            "parcel_gps.gpkg",
            "GeoPackage (*.gpkg);;GeoJSON (*.geojson);;ESRI Shapefile (*.shp);;KML (*.kml)",
        )
        if not path:
            return
        extension = os.path.splitext(path)[1].lower()
        if extension not in SAVE_DRIVERS:
            path, extension = f"{path}.gpkg", ".gpkg"
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = SAVE_DRIVERS[extension]
        options.fileEncoding = "UTF-8"
        options.layerName = "parcel_gps"
        result = QgsVectorFileWriter.writeAsVectorFormatV3(
            layer, path, QgsProject.instance().transformContext(), options
        )
        if result[0] == QgsVectorFileWriter.WriterError.NoError:
            self._show_status(tr("Results saved to {path}").format(path=html.escape(path)))
        else:
            self._show_status(
                tr("Could not save the results: {detail}").format(detail=html.escape(str(result[1]))), error=True
            )


def _plain(value):
    if value is None:
        return None
    is_null = getattr(value, "isNull", None)
    if callable(is_null) and is_null():
        return None
    return value
