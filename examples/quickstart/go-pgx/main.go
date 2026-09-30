// Minimal Kisenon connection example (Go + pgx v5).
//
//	export DATABASE_URL='postgresql://<role>:<password>@<endpoint>.kisenon.com:5432/main?sslmode=require'
//	go run .
package main

import (
	"context"
	"fmt"
	"os"
	"time"

	"github.com/jackc/pgx/v5"
)

func main() {
	url := os.Getenv("DATABASE_URL")
	if url == "" {
		fmt.Fprintln(os.Stderr, "DATABASE_URL is required. Copy it from kisenon.com -> project -> branch -> endpoint.")
		os.Exit(1)
	}
	ctx := context.Background()
	conn, err := pgx.Connect(ctx, url)
	if err != nil {
		fmt.Fprintln(os.Stderr, "connect:", err)
		os.Exit(1)
	}
	defer conn.Close(ctx)

	var now time.Time
	var version string
	if err := conn.QueryRow(ctx, "SELECT now(), version()").Scan(&now, &version); err != nil {
		fmt.Fprintln(os.Stderr, "query:", err)
		os.Exit(1)
	}
	fmt.Printf("now:     %s\nversion: %s\n", now.Format(time.RFC3339Nano), version)
}
