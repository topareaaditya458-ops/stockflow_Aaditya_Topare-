from database.connection import Base, engine
from database.models import Product, Sale, SaleItem

Base.metadata.create_all(bind=engine)

print('StockFlow database tables checked successfully!')

print('Tables:')

for table_name in Base.metadata.tables:
    print(f'- {table_name}')