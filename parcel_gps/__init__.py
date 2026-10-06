def classFactory(iface):
    from .plugin import ParcelGpsPlugin

    return ParcelGpsPlugin(iface)
