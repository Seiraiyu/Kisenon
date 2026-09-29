-- Demo change: drop returned orders from the orders mart. Copy over
-- jaffle/models/marts/orders.sql and run `dbt-branch-ci check` to see the
-- ~17% row drop trip the default 10% threshold.
with payments as (
    select order_id, sum(amount) as amount
    from {{ ref('stg_payments') }}
    group by order_id
)

select o.order_id, o.customer_id, o.order_date, o.status, coalesce(p.amount, 0) as amount
from {{ ref('stg_orders') }} as o
left join payments as p using (order_id)
where o.status <> 'returned'
