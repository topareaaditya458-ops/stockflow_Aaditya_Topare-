from datetime import datetime

from sqlalchemy import (
    String,
    Integer,
    Float,
    DateTime,
    ForeignKey,
    CheckConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.connection import Base


class Product(Base):
    __tablename__ = 'products'

    id: Mapped[int] = mapped_column(primary_key=True)

    sku: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True
    )

    name: Mapped[str] = mapped_column(
        String(150),
        index=True
    )

    category: Mapped[str] = mapped_column(String(100))

    purchase_price: Mapped[float] = mapped_column(
        Float,
        default=0
    )

    selling_price: Mapped[float] = mapped_column(Float)

    # GST configuration
    gst_rate: Mapped[float] = mapped_column(
        Float,
        default=18.0,
        nullable=False
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        default=0
    )

    minimum_stock: Mapped[int] = mapped_column(
        Integer,
        default=5
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now
    )

    __table_args__ = (
        CheckConstraint(
            'quantity >= 0',
            name='check_product_quantity'
        ),
        CheckConstraint(
            'purchase_price >= 0 AND selling_price >= 0',
            name='check_product_prices'
        ),
        CheckConstraint(
            'gst_rate >= 0 AND gst_rate <= 100',
            name='check_product_gst_rate'
        ),
    )


class Sale(Base):
    __tablename__ = 'sales'

    id: Mapped[int] = mapped_column(primary_key=True)

    invoice_number: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True
    )

    # Pricing and tax summary
    subtotal: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False
    )

    discount_type: Mapped[str] = mapped_column(
        String(20),
        default='none',
        nullable=False
    )

    discount_value: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False
    )

    discount_amount: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False
    )

    taxable_amount: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False
    )

    gst_amount: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False
    )

    pricing_mode: Mapped[str] = mapped_column(
        String(20),
        default='exclusive',
        nullable=False
    )

    total_amount: Mapped[float] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        index=True
    )

    items: Mapped[list['SaleItem']] = relationship(
        back_populates='sale',
        cascade='all, delete-orphan'
    )

    __table_args__ = (
        CheckConstraint(
            'subtotal >= 0',
            name='check_sale_subtotal'
        ),
        CheckConstraint(
            'discount_amount >= 0',
            name='check_sale_discount_amount'
        ),
        CheckConstraint(
            'taxable_amount >= 0',
            name='check_sale_taxable_amount'
        ),
        CheckConstraint(
            'gst_amount >= 0',
            name='check_sale_gst_amount'
        ),
    )


class SaleItem(Base):
    __tablename__ = 'sale_items'

    id: Mapped[int] = mapped_column(primary_key=True)

    sale_id: Mapped[int] = mapped_column(
        ForeignKey('sales.id', ondelete='CASCADE')
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey('products.id')
    )

    quantity: Mapped[int] = mapped_column(Integer)

    # Historical values captured at the time of sale
    unit_price: Mapped[float] = mapped_column(Float)

    subtotal: Mapped[float] = mapped_column(Float)

    gst_rate: Mapped[float] = mapped_column(
        Float,
        default=18.0,
        nullable=False
    )

    discount_amount: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False
    )

    taxable_amount: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False
    )

    gst_amount: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False
    )

    total_amount: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False
    )

    sale: Mapped[Sale] = relationship(
        back_populates='items'
    )

    product: Mapped[Product] = relationship()

    __table_args__ = (
        CheckConstraint(
            'quantity > 0',
            name='check_sale_item_quantity'
        ),
        CheckConstraint(
            'unit_price >= 0',
            name='check_sale_item_price'
        ),
        CheckConstraint(
            'gst_rate >= 0 AND gst_rate <= 100',
            name='check_sale_item_gst_rate'
        ),
    )