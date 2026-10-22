from decimal import Decimal, ROUND_HALF_UP


CENT = Decimal('0.01')


def money(value):
    """Convert a value into a Decimal rounded to two decimal places."""
    return Decimal(str(value)).quantize(
        CENT,
        rounding=ROUND_HALF_UP
    )


def calculate_invoice(
    items,
    pricing_mode='exclusive',
    discount_type='none',
    discount_value=0
):
    """
    Calculate invoice totals for GST-inclusive or GST-exclusive pricing.

    Each item must contain:
        product_id
        name
        quantity
        unit_price
        gst_rate

    discount_type:
        none
        percentage
        fixed

    pricing_mode:
        exclusive: unit price does not include GST
        inclusive: unit price already includes GST

    Discounts are allocated proportionally across line items.
    """

    if pricing_mode not in ('inclusive', 'exclusive'):
        raise ValueError(
            'Pricing mode must be inclusive or exclusive.'
        )

    if discount_type not in ('none', 'percentage', 'fixed'):
        raise ValueError(
            'Discount type must be none, percentage, or fixed.'
        )

    discount_value = money(discount_value)

    if discount_value < 0:
        raise ValueError('Discount cannot be negative.')

    if discount_type == 'percentage' and discount_value > 100:
        raise ValueError('Percentage discount cannot exceed 100%.')

    if discount_type == 'none' and discount_value != 0:
        raise ValueError('Discount value must be zero when discount type is none.')

    if not items:
        raise ValueError('Add at least one product to the invoice.')

    prepared_items = []
    subtotal = Decimal('0.00')

    for item in items:
        quantity = int(item['quantity'])
        unit_price = money(item['unit_price'])
        gst_rate = Decimal(str(item['gst_rate']))

        if quantity <= 0:
            raise ValueError('Quantity must be greater than zero.')

        if unit_price < 0:
            raise ValueError('Unit price cannot be negative.')

        if gst_rate < 0 or gst_rate > 100:
            raise ValueError('GST rate must be between 0 and 100.')

        line_subtotal = money(unit_price * quantity)
        subtotal += line_subtotal

        prepared_items.append({
            'product_id': item['product_id'],
            'name': item['name'],
            'quantity': quantity,
            'unit_price': unit_price,
            'gst_rate': gst_rate,
            'subtotal': line_subtotal
        })

    subtotal = money(subtotal)

    if discount_type == 'percentage':
        discount_amount = money(
            subtotal * discount_value / Decimal('100')
        )
    elif discount_type == 'fixed':
        discount_amount = discount_value
    else:
        discount_amount = Decimal('0.00')

    if discount_amount > subtotal:
        raise ValueError(
            'Discount cannot exceed the invoice subtotal.'
        )

    # Allocate the invoice discount proportionally.
    allocated_discount = Decimal('0.00')

    for index, item in enumerate(prepared_items):
        if index == len(prepared_items) - 1:
            line_discount = money(
                discount_amount - allocated_discount
            )
        elif subtotal > 0:
            line_discount = money(
                discount_amount * item['subtotal'] / subtotal
            )
            allocated_discount += line_discount
        else:
            line_discount = Decimal('0.00')

        item['discount_amount'] = line_discount

        if pricing_mode == 'exclusive':
            # Selling price excludes GST.
            item['taxable_amount'] = money(
                item['subtotal'] - line_discount
            )

            item['gst_amount'] = money(
                item['taxable_amount']
                * item['gst_rate']
                / Decimal('100')
            )

            item['total_amount'] = money(
                item['taxable_amount'] + item['gst_amount']
            )

        else:
            # Selling price already includes GST.
            # Extract the taxable amount after discount.
            item['total_amount'] = money(
                item['subtotal'] - line_discount
            )

            divisor = Decimal('1') + (
                item['gst_rate'] / Decimal('100')
            )

            if divisor == 0:
                raise ValueError('Invalid GST calculation.')

            item['taxable_amount'] = money(
                item['total_amount'] / divisor
            )

            item['gst_amount'] = money(
                item['total_amount'] - item['taxable_amount']
            )

    taxable_amount = money(
        sum(
            (item['taxable_amount'] for item in prepared_items),
            Decimal('0.00')
        )
    )

    gst_amount = money(
        sum(
            (item['gst_amount'] for item in prepared_items),
            Decimal('0.00')
        )
    )

    total_amount = money(
        sum(
            (item['total_amount'] for item in prepared_items),
            Decimal('0.00')
        )
    )

    return {
        'items': prepared_items,
        'subtotal': subtotal,
        'discount_type': discount_type,
        'discount_value': discount_value,
        'discount_amount': discount_amount,
        'taxable_amount': taxable_amount,
        'gst_amount': gst_amount,
        'pricing_mode': pricing_mode,
        'total_amount': total_amount
    }