// Minimal Kisenon connection example (Rust + sqlx).
//
//   export DATABASE_URL='postgresql://<role>:<password>@<endpoint>.kisenon.com:5432/main?sslmode=require'
//   cargo run
use chrono::{DateTime, Utc};
use sqlx::{Connection, PgConnection};

#[tokio::main]
async fn main() -> Result<(), sqlx::Error> {
    let Ok(url) = std::env::var("DATABASE_URL") else {
        eprintln!("DATABASE_URL is required. Copy it from kisenon.com -> project -> branch -> endpoint.");
        std::process::exit(1);
    };
    let mut conn = PgConnection::connect(&url).await?;

    let (now, version): (DateTime<Utc>, String) =
        sqlx::query_as("SELECT now(), version()").fetch_one(&mut conn).await?;

    println!("now:     {now}\nversion: {version}");
    conn.close().await
}
