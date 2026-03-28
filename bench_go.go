package main

import (
	"fmt"
	"net/http"
	"time"

	"github.com/julienschmidt/httprouter"
)

func dummy(w http.ResponseWriter, r *http.Request, _ httprouter.Params) {}

func main() {
	router := httprouter.New()

	// Same routes as the Zig benchmark
	router.GET("/", dummy)
	router.GET("/health", dummy)
	router.GET("/api/v1/users", dummy)
	router.GET("/api/v1/users/:id", dummy)
	router.POST("/api/v1/users", dummy)
	router.PUT("/api/v1/users/:id", dummy)
	router.DELETE("/api/v1/users/:id", dummy)
	router.GET("/api/v1/users/:id/posts", dummy)
	router.GET("/api/v1/users/:id/posts/:post_id", dummy)
	router.GET("/api/v1/items", dummy)
	router.GET("/api/v1/items/:cat/:id", dummy)
	router.POST("/api/v1/items", dummy)
	router.GET("/api/v1/search", dummy)
	router.GET("/docs", dummy)
	router.GET("/openapi.json", dummy)

	type lookup struct {
		method string
		path   string
	}

	lookups := []lookup{
		{"GET", "/"},
		{"GET", "/health"},
		{"GET", "/api/v1/users"},
		{"GET", "/api/v1/users/42"},
		{"POST", "/api/v1/users"},
		{"GET", "/api/v1/users/42/posts"},
		{"GET", "/api/v1/users/42/posts/7"},
		{"GET", "/api/v1/items/books/99"},
		{"GET", "/api/v1/search"},
		{"GET", "/docs"},
		{"GET", "/nonexistent"},
	}

	iters := 5_000_000

	// Warmup
	for i := 0; i < 100_000; i++ {
		for _, l := range lookups {
			req, _ := http.NewRequest(l.method, l.path, nil)
			router.ServeHTTP(nil, req)
		}
	}

	// Benchmark
	total := 0
	start := time.Now()

	for i := 0; i < iters; i++ {
		for _, l := range lookups {
			_, _, _ = router.Lookup(l.method, l.path)
			total++
		}
	}

	elapsed := time.Since(start)
	nsPerOp := elapsed.Nanoseconds() / int64(total)
	opsPerSec := int64(0)
	if nsPerOp > 0 {
		opsPerSec = 1_000_000_000 / nsPerOp
	}

	fmt.Printf("\nhttprouter (Go) — radix trie\n")
	fmt.Printf("  %d lookups/sec   %dns avg\n\n", opsPerSec, nsPerOp)
}
