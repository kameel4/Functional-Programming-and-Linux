from astroquery.mast import Observations

# поиск снимков в области вокруг объекта (например, M51)
obs = Observations.query_object("M51", radius="0.05 deg")

# фильтруем по продуктам типа image (FITS)
products = Observations.get_product_list(obs)
fits_products = Observations.filter_products(products, productSubGroupDescription="FITS")

# качаем первые 5 больших файлов
download = Observations.download_products(fits_products[:5], mrp_only=False)
print("Saved to:", download['Local Path'])
