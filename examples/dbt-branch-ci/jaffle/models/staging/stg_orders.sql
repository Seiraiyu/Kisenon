select id as order_id, customer_id, order_date::date as order_date, status
from {{ ref('raw_orders') }}
