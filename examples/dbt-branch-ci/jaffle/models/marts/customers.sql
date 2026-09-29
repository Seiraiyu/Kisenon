select
    c.customer_id,
    c.first_name,
    c.last_name,
    count(o.order_id) as number_of_orders,
    min(o.order_date) as first_order,
    max(o.order_date) as most_recent_order,
    coalesce(sum(o.amount), 0) as lifetime_value
from {{ ref('stg_customers') }} as c
left join {{ ref('orders') }} as o using (customer_id)
group by c.customer_id, c.first_name, c.last_name
