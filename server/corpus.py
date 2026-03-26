"""
Realistic pull request corpus with ground-truth bug and security annotations.
Each PR has a ground_truth dict that the grader uses to score the agent.

Difficulty bands:
  easy   (bug_detection)   — obvious logic errors, clear bugs, surface-level issues
  medium (security_audit)  — security vulnerabilities requiring domain knowledge
  hard   (full_review)     — subtle bugs + security + design issues interleaved
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from .models import (
    FileDiff, PullRequest,
    BugCategory, SecurityCategory, Severity, ReviewerRole,
)


@dataclass
class GroundTruth:
    """What a perfect reviewer would find in this PR."""
    bugs: list[dict[str, Any]] = field(default_factory=list)          # {line, category, severity}
    security_issues: list[dict[str, Any]] = field(default_factory=list)  # {line, category, severity}
    correct_reviewer: ReviewerRole = ReviewerRole.BACKEND
    should_approve: bool = False          # True only if PR has no blocking issues
    quality_comments: list[str] = field(default_factory=list)  # expected comment topics


@dataclass
class AnnotatedPR:
    pr: PullRequest
    ground_truth: GroundTruth
    difficulty: str   # easy | medium | hard


# ═══════════════════════════════════════════════════════════════════════════════
# EASY PRs — Bug Detection
# ═══════════════════════════════════════════════════════════════════════════════

EASY_PR_1 = AnnotatedPR(
    pr=PullRequest(
        pr_id="PR-101",
        title="Add user pagination to /api/users endpoint",
        description="Implements cursor-based pagination for the user listing endpoint. Adds `limit` and `offset` query params.",
        author="junior_dev_1",
        files=[
            FileDiff(
                filename="api/users.py",
                language="python",
                patch='''\
--- a/api/users.py
+++ b/api/users.py
@@ -1,20 +1,35 @@
 from flask import Flask, request, jsonify
 from db import get_db

 app = Flask(__name__)

+DEFAULT_LIMIT = 20
+MAX_LIMIT = 100
+
 @app.route('/api/users')
 def list_users():
     db = get_db()
-    users = db.query("SELECT * FROM users")
-    return jsonify(users)
+    limit = int(request.args.get('limit', DEFAULT_LIMIT))
+    offset = int(request.args.get('offset', 0))
+
+    if limit > MAX_LIMIT:
+        limit = MAX_LIMIT
+
+    users = db.query(
+        f"SELECT * FROM users LIMIT {limit} OFFSET {offset}"
+    )
+
+    total = db.query("SELECT COUNT(*) FROM users")[0]['count']
+
+    return jsonify({
+        'users': users,
+        'total': total,
+        'limit': limit,
+        'offset': offset,
+        'has_more': (offset + limit) < total
+    })
+
+@app.route('/api/users/<int:user_id>')
+def get_user(user_id):
+    db = get_db()
+    user = db.query(f"SELECT * FROM users WHERE id = {user_id}")
+    if not user:
+        return jsonify({'error': 'not found'}), 404
+    return jsonify(user[0])
''',
                additions=25,
                deletions=3,
            ),
            FileDiff(
                filename="api/utils.py",
                language="python",
                patch='''\
--- a/api/utils.py
+++ b/api/utils.py
@@ -1,10 +1,25 @@
 def paginate(items, page, per_page):
-    return items
+    start = (page - 1) * per_page
+    end = start + per_page
+    return items[start:end]
+
+def calculate_discount(price, discount_percent):
+    """Apply a percentage discount to a price."""
+    if discount_percent < 0 or discount_percent > 100:
+        raise ValueError("Discount must be between 0 and 100")
+    discounted = price - (price * discount_percent / 100)
+    return round(discounted, 2)
+
+def is_valid_email(email: str) -> bool:
+    """Basic email validation."""
+    return '@' in email and '.' in email.split('@')[-1]
+
+def retry(func, max_attempts=3):
+    """Retry a function up to max_attempts times."""
+    for attempt in range(max_attempts):
+        try:
+            return func()
+        except Exception as e:
+            if attempt == max_attempts:   # BUG: should be max_attempts - 1
+                raise
+            continue
''',
                additions=20,
                deletions=1,
            ),
        ],
        language="python",
        total_additions=45,
        total_deletions=4,
    ),
    ground_truth=GroundTruth(
        bugs=[
            {
                "line": 22,        # attempt == max_attempts never true (off-by-one)
                "category": BugCategory.OFF_BY_ONE,
                "severity": Severity.MEDIUM,
                "file": "api/utils.py",
                "description": "attempt == max_attempts is never true; last attempt index is max_attempts-1, so exception is never re-raised"
            },
        ],
        security_issues=[
            {
                "line": 17,        # f-string SQL in get_user
                "category": SecurityCategory.SQL_INJECTION,
                "severity": Severity.HIGH,
                "file": "api/users.py",
                "description": "Direct f-string interpolation of user_id into SQL query"
            },
        ],
        correct_reviewer=ReviewerRole.BACKEND,
        should_approve=False,
        quality_comments=["sql injection", "parameterized query", "off by one", "retry logic"],
    ),
    difficulty="easy",
)


EASY_PR_2 = AnnotatedPR(
    pr=PullRequest(
        pr_id="PR-102",
        title="Implement shopping cart total calculation",
        description="Adds cart total with discount and tax calculation for checkout flow.",
        author="junior_dev_2",
        files=[
            FileDiff(
                filename="cart/calculator.js",
                language="javascript",
                patch='''\
--- a/cart/calculator.js
+++ b/cart/calculator.js
@@ -0,0 +1,52 @@
+/**
+ * Shopping cart price calculator
+ */
+
+const TAX_RATE = 0.08;
+
+function calculateCartTotal(items) {
+    let total = 0;
+    for (let i = 0; i <= items.length; i++) {  // BUG: should be <
+        total += items[i].price * items[i].quantity;
+    }
+    return total;
+}
+
+function applyDiscount(total, couponCode) {
+    const discounts = {
+        'SAVE10': 0.10,
+        'SAVE20': 0.20,
+        'HALFOFF': 0.50,
+    };
+    const rate = discounts[couponCode] || 0;
+    return total * (1 - rate);
+}
+
+function addTax(subtotal) {
+    return subtotal * (1 + TAX_RATE);
+}
+
+function checkout(items, couponCode) {
+    const subtotal = calculateCartTotal(items);
+    const discounted = applyDiscount(subtotal, couponCode);
+    const total = addTax(discounted);
+    return {
+        subtotal: subtotal.toFixed(2),
+        discount: (subtotal - discounted).toFixed(2),
+        tax: (total - discounted).toFixed(2),
+        total: total.toFixed(2),
+    };
+}
+
+async function processPayment(cartId, paymentInfo) {
+    const response = await fetch('/api/payment', {
+        method: 'POST',
+        body: JSON.stringify({
+            cart_id: cartId,
+            card_number: paymentInfo.cardNumber,
+            cvv: paymentInfo.cvv,
+            amount: paymentInfo.amount,
+        })
+    });
+    return response.json();
+}
+
+module.exports = { calculateCartTotal, applyDiscount, addTax, checkout, processPayment };
''',
                additions=52,
                deletions=0,
            ),
        ],
        language="javascript",
        total_additions=52,
        total_deletions=0,
    ),
    ground_truth=GroundTruth(
        bugs=[
            {
                "line": 9,
                "category": BugCategory.OFF_BY_ONE,
                "severity": Severity.HIGH,
                "file": "cart/calculator.js",
                "description": "Loop uses <= items.length causing out-of-bounds access on last iteration"
            },
        ],
        security_issues=[
            {
                "line": 43,
                "category": SecurityCategory.SENSITIVE_DATA_EXPOSURE,
                "severity": Severity.CRITICAL,
                "file": "cart/calculator.js",
                "description": "Raw CVV and card number sent to backend over plain fetch with no mention of HTTPS enforcement; CVV should never be logged or stored"
            },
        ],
        correct_reviewer=ReviewerRole.SECURITY,
        should_approve=False,
        quality_comments=["off by one", "cvv", "pci", "card data", "payment security"],
    ),
    difficulty="easy",
)


# ═══════════════════════════════════════════════════════════════════════════════
# MEDIUM PRs — Security Audit
# ═══════════════════════════════════════════════════════════════════════════════

MEDIUM_PR_1 = AnnotatedPR(
    pr=PullRequest(
        pr_id="PR-201",
        title="Add file export and report download feature",
        description="Users can now export their data as CSV/JSON and download generated reports by filename.",
        author="mid_dev_1",
        files=[
            FileDiff(
                filename="api/export.py",
                language="python",
                patch='''\
--- a/api/export.py
+++ b/api/export.py
@@ -0,0 +1,68 @@
+import os
+import csv
+import json
+import subprocess
+from flask import Flask, request, send_file, jsonify
+from auth import require_login
+
+EXPORT_DIR = "/var/app/exports"
+REPORTS_DIR = "/var/app/reports"
+
+@app.route('/api/export/download')
+@require_login
+def download_report():
+    """Download a generated report by filename."""
+    filename = request.args.get('filename')
+    if not filename:
+        return jsonify({'error': 'filename required'}), 400
+
+    filepath = os.path.join(REPORTS_DIR, filename)
+    return send_file(filepath)   # VULN: path traversal
+
+@app.route('/api/export/csv')
+@require_login
+def export_csv():
+    user_id = request.args.get('user_id')
+    db = get_db()
+    rows = db.query(f"SELECT * FROM user_data WHERE user_id = {user_id}")
+    # write to temp file and return
+    outpath = f"{EXPORT_DIR}/{user_id}_export.csv"
+    with open(outpath, 'w') as f:
+        writer = csv.writer(f)
+        if rows:
+            writer.writerow(rows[0].keys())
+            writer.writerows([r.values() for r in rows])
+    return send_file(outpath, mimetype='text/csv')
+
+@app.route('/api/export/run-report', methods=['POST'])
+@require_login
+def run_report():
+    """Run a named report generator script."""
+    report_name = request.json.get('report_name', '')
+    output_format = request.json.get('format', 'csv')
+    cmd = f"python /var/app/scripts/{report_name}.py --format {output_format}"
+    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
+    return jsonify({'output': result.stdout, 'errors': result.stderr})
+
+@app.route('/api/export/preview')
+@require_login
+def preview_export():
+    template = request.args.get('template', '')
+    # render a jinja-like template for preview
+    import jinja2
+    env_j2 = jinja2.Environment()
+    rendered = env_j2.from_string(template).render()  # VULN: SSTI
+    return rendered
+
+SECRET_KEY = "sk-prod-8f2a91bc4e7d3f0a"   # VULN: hardcoded secret
+DB_PASSWORD = "prod_mysql_P@ssw0rd123"
+
+def get_signed_url(bucket, key):
+    """Generate a pre-signed S3 URL."""
+    import boto3
+    s3 = boto3.client(
+        's3',
+        aws_access_key_id='AKIAIOSFODNN7EXAMPLE',         # VULN: hardcoded AWS key
+        aws_secret_access_key='wJalrXUtnFEMI/K7MDENG',
+    )
+    return s3.generate_presigned_url('get_object', Params={'Bucket': bucket, 'Key': key})
''',
                additions=68,
                deletions=0,
            ),
        ],
        language="python",
        total_additions=68,
        total_deletions=0,
    ),
    ground_truth=GroundTruth(
        bugs=[],
        security_issues=[
            {
                "line": 19,
                "category": SecurityCategory.PATH_TRAVERSAL,
                "severity": Severity.CRITICAL,
                "file": "api/export.py",
                "description": "filename from user input joined directly to REPORTS_DIR; attacker can use ../../../etc/passwd"
            },
            {
                "line": 27,
                "category": SecurityCategory.SQL_INJECTION,
                "severity": Severity.CRITICAL,
                "file": "api/export.py",
                "description": "user_id interpolated directly into SQL query string"
            },
            {
                "line": 42,
                "category": SecurityCategory.COMMAND_INJECTION,
                "severity": Severity.CRITICAL,
                "file": "api/export.py",
                "description": "report_name and format from user input fed into shell=True subprocess; allows arbitrary command execution"
            },
            {
                "line": 51,
                "category": SecurityCategory.XSS,       # closest to SSTI
                "severity": Severity.HIGH,
                "file": "api/export.py",
                "description": "Jinja2 Environment() without sandboxing renders user-supplied template; Server-Side Template Injection"
            },
            {
                "line": 55,
                "category": SecurityCategory.HARDCODED_SECRET,
                "severity": Severity.CRITICAL,
                "file": "api/export.py",
                "description": "Hardcoded SECRET_KEY and DB_PASSWORD in source code"
            },
            {
                "line": 63,
                "category": SecurityCategory.HARDCODED_SECRET,
                "severity": Severity.CRITICAL,
                "file": "api/export.py",
                "description": "AWS access key ID and secret hardcoded; will be exposed in version control"
            },
        ],
        correct_reviewer=ReviewerRole.SECURITY,
        should_approve=False,
        quality_comments=["path traversal", "sql injection", "command injection", "ssti", "hardcoded secret", "aws key"],
    ),
    difficulty="medium",
)


MEDIUM_PR_2 = AnnotatedPR(
    pr=PullRequest(
        pr_id="PR-202",
        title="Implement JWT authentication and session management",
        description="Adds JWT-based login, token refresh, and role-based access control middleware.",
        author="mid_dev_2",
        files=[
            FileDiff(
                filename="auth/jwt_handler.go",
                language="go",
                patch='''\
--- a/auth/jwt_handler.go
+++ b/auth/jwt_handler.go
@@ -0,0 +1,85 @@
+package auth
+
+import (
+    "fmt"
+    "time"
+    "crypto/md5"
+    "encoding/json"
+    "net/http"
+    "strings"
+)
+
+var jwtSecret = []byte("secret123")  // VULN: weak hardcoded secret
+
+type Claims struct {
+    UserID   int    `json:"user_id"`
+    Role     string `json:"role"`
+    IsAdmin  bool   `json:"is_admin"`
+}
+
+// GenerateToken creates a JWT for the given user.
+func GenerateToken(userID int, role string, isAdmin bool) (string, error) {
+    claims := Claims{UserID: userID, Role: role, IsAdmin: isAdmin}
+    header := base64Encode(`{"alg":"HS256","typ":"JWT"}`)
+    payload := base64Encode(toJSON(claims))
+    sig := fmt.Sprintf("%x", md5.Sum([]byte(header+"."+payload)))  // VULN: MD5, not HMAC
+    return header + "." + payload + "." + sig, nil
+}
+
+// ValidateToken parses and validates a JWT.
+func ValidateToken(token string) (*Claims, error) {
+    parts := strings.Split(token, ".")
+    if len(parts) != 3 {
+        return nil, fmt.Errorf("invalid token")
+    }
+    // VULN: signature is never actually verified against the secret
+    payload, _ := base64Decode(parts[1])
+    var claims Claims
+    json.Unmarshal(payload, &claims)
+    return &claims, nil
+}
+
+// RequireAdmin middleware — allows access only if is_admin is true in the token
+func RequireAdmin(next http.HandlerFunc) http.HandlerFunc {
+    return func(w http.ResponseWriter, r *http.Request) {
+        token := r.Header.Get("Authorization")
+        claims, err := ValidateToken(token)  // VULN: unverified claims trusted
+        if err != nil || !claims.IsAdmin {
+            http.Error(w, "Forbidden", 403)
+            return
+        }
+        next(w, r)
+    }
+}
+
+func HashPassword(password string) string {
+    return fmt.Sprintf("%x", md5.Sum([]byte(password)))  // VULN: MD5 for password hashing
+}
+
+func CheckPassword(password, hash string) bool {
+    return HashPassword(password) == hash
+}
+
+// GetUserFromDB retrieves a user by credentials.
+func GetUserFromDB(db interface{}, username, password string) (int, error) {
+    query := fmt.Sprintf(
+        "SELECT id FROM users WHERE username='%s' AND password='%s'",
+        username, HashPassword(password),   // VULN: SQL injection
+    )
+    // execute query...
+    _ = query
+    return 0, nil
+}
+
+func RefreshToken(oldToken string) (string, error) {
+    claims, err := ValidateToken(oldToken)
+    if err != nil {
+        return "", err
+    }
+    // no expiry check — VULN: expired tokens can be refreshed indefinitely
+    return GenerateToken(claims.UserID, claims.Role, claims.IsAdmin)
+}
''',
                additions=85,
                deletions=0,
            ),
        ],
        language="go",
        total_additions=85,
        total_deletions=0,
    ),
    ground_truth=GroundTruth(
        bugs=[
            {
                "line": 65,
                "category": BugCategory.LOGIC_ERROR,
                "severity": Severity.HIGH,
                "file": "auth/jwt_handler.go",
                "description": "RefreshToken never checks token expiry; expired tokens can be refreshed forever"
            },
        ],
        security_issues=[
            {
                "line": 12,
                "category": SecurityCategory.HARDCODED_SECRET,
                "severity": Severity.CRITICAL,
                "file": "auth/jwt_handler.go",
                "description": "JWT secret is a weak hardcoded string literal"
            },
            {
                "line": 25,
                "category": SecurityCategory.BROKEN_AUTH,
                "severity": Severity.CRITICAL,
                "file": "auth/jwt_handler.go",
                "description": "Token signed with MD5 instead of HMAC-SHA256; MD5 is cryptographically broken"
            },
            {
                "line": 34,
                "category": SecurityCategory.BROKEN_AUTH,
                "severity": Severity.CRITICAL,
                "file": "auth/jwt_handler.go",
                "description": "ValidateToken never verifies the signature; any crafted token is accepted"
            },
            {
                "line": 53,
                "category": SecurityCategory.BROKEN_AUTH,
                "severity": Severity.HIGH,
                "file": "auth/jwt_handler.go",
                "description": "MD5 used for password hashing; must use bcrypt/argon2"
            },
            {
                "line": 61,
                "category": SecurityCategory.SQL_INJECTION,
                "severity": Severity.CRITICAL,
                "file": "auth/jwt_handler.go",
                "description": "username and password interpolated directly into SQL string"
            },
        ],
        correct_reviewer=ReviewerRole.SECURITY,
        should_approve=False,
        quality_comments=["signature verification", "md5", "bcrypt", "sql injection", "token expiry", "hardcoded secret"],
    ),
    difficulty="medium",
)


# ═══════════════════════════════════════════════════════════════════════════════
# HARD PRs — Full Review (bugs + security + design interleaved)
# ═══════════════════════════════════════════════════════════════════════════════

HARD_PR_1 = AnnotatedPR(
    pr=PullRequest(
        pr_id="PR-301",
        title="Async job queue with worker pool and result caching",
        description="Implements a background job processing system with Redis-backed queue, thread-pool workers, and in-memory result cache.",
        author="senior_dev_1",
        files=[
            FileDiff(
                filename="workers/job_queue.py",
                language="python",
                patch='''\
--- a/workers/job_queue.py
+++ b/workers/job_queue.py
@@ -0,0 +1,110 @@
+import threading
+import pickle
+import redis
+import time
+import logging
+from typing import Any, Callable
+
+logger = logging.getLogger(__name__)
+
+# Shared result cache — NOT thread-safe
+_result_cache: dict = {}
+_cache_lock = threading.Lock()   # lock exists but is inconsistently used
+
+class JobQueue:
+    def __init__(self, redis_url: str):
+        self.redis = redis.from_url(redis_url)
+        self.workers: list[threading.Thread] = []
+        self._running = False
+
+    def enqueue(self, job_id: str, func: Callable, *args, **kwargs) -> None:
+        """Serialize and push a job onto the queue."""
+        payload = pickle.dumps({'func': func, 'args': args, 'kwargs': kwargs})
+        self.redis.rpush('job_queue', payload)   # VULN: pickle deserialization of untrusted data
+
+    def _worker_loop(self) -> None:
+        while self._running:
+            raw = self.redis.blpop('job_queue', timeout=1)
+            if raw is None:
+                continue
+            _, payload = raw
+            job = pickle.loads(payload)          # VULN: deserializing untrusted pickle from Redis
+            try:
+                result = job['func'](*job['args'], **job['kwargs'])
+                # Store without lock — RACE CONDITION
+                _result_cache[job['func'].__name__] = result
+            except Exception as e:
+                logger.error(f"Job failed: {e}")
+
+    def start(self, num_workers: int = 4) -> None:
+        self._running = True
+        for _ in range(num_workers):
+            t = threading.Thread(target=self._worker_loop, daemon=True)
+            t.start()
+            self.workers.append(t)
+
+    def stop(self) -> None:
+        self._running = False
+        for t in self.workers:
+            t.join(timeout=5)
+        # BUG: workers list never cleared; calling start() again doubles workers
+
+    def get_result(self, func_name: str) -> Any:
+        # No lock here — another race condition on read
+        return _result_cache.get(func_name)
+
+
+class RateLimiter:
+    """Token bucket rate limiter."""
+    def __init__(self, rate: int, capacity: int):
+        self.rate = rate          # tokens per second
+        self.capacity = capacity
+        self.tokens = capacity
+        self.last_refill = time.time()
+        self._lock = threading.Lock()
+
+    def allow(self) -> bool:
+        with self._lock:
+            now = time.time()
+            elapsed = now - self.last_refill
+            self.tokens = min(
+                self.capacity,
+                self.tokens + elapsed * self.rate
+            )
+            self.last_refill = now
+            if self.tokens >= 1:
+                self.tokens -= 1
+                return True
+            return False
+
+
+def schedule_recurring(func: Callable, interval_seconds: int) -> threading.Thread:
+    """Schedule a function to run every interval_seconds."""
+    def loop():
+        while True:
+            func()
+            time.sleep(interval_seconds)
+    t = threading.Thread(target=loop, daemon=True)
+    t.start()
+    return t
+    # BUG: no way to stop this thread; memory leak if called repeatedly
+
+
+def run_with_timeout(func: Callable, timeout: int, *args) -> Any:
+    """Run func in a thread and return result or raise TimeoutError."""
+    result = [None]
+    exception = [None]
+
+    def target():
+        try:
+            result[0] = func(*args)
+        except Exception as e:
+            exception[0] = e
+
+    t = threading.Thread(target=target)
+    t.start()
+    t.join(timeout=timeout)
+    if t.is_alive():
+        # BUG: thread is still running after timeout; no actual cancellation
+        raise TimeoutError(f"Function timed out after {timeout}s")
+    if exception[0]:
+        raise exception[0]
+    return result[0]
''',
                additions=110,
                deletions=0,
            ),
            FileDiff(
                filename="workers/cache.py",
                language="python",
                patch='''\
--- a/workers/cache.py
+++ b/workers/cache.py
@@ -0,0 +1,40 @@
+import time
+from typing import Any, Optional
+
+class TTLCache:
+    """Simple in-memory cache with TTL eviction."""
+
+    def __init__(self, ttl_seconds: int = 300):
+        self.ttl = ttl_seconds
+        self._store: dict[str, tuple[Any, float]] = {}
+
+    def set(self, key: str, value: Any) -> None:
+        self._store[key] = (value, time.time())
+
+    def get(self, key: str) -> Optional[Any]:
+        entry = self._store.get(key)
+        if entry is None:
+            return None
+        value, ts = entry
+        if time.time() - ts > self.ttl:
+            # expired — but NOT deleted from store (memory leak)
+            return None
+        return value
+
+    def clear_expired(self) -> int:
+        now = time.time()
+        expired = [k for k, (_, ts) in self._store.items() if now - ts > self.ttl]
+        for k in expired:
+            del self._store[k]
+        return len(expired)
+
+    def get_or_set(self, key: str, func: Callable, *args) -> Any:
+        val = self.get(key)
+        if val is not None:
+            return val
+        # BUG: not thread-safe; stampede problem — multiple threads can call func() simultaneously
+        result = func(*args)
+        self.set(key, result)
+        return result
+
+    def size(self) -> int:
+        return len(self._store)  # BUG: includes expired entries — misleading metric
''',
                additions=40,
                deletions=0,
            ),
        ],
        language="python",
        total_additions=150,
        total_deletions=0,
    ),
    ground_truth=GroundTruth(
        bugs=[
            {
                "line": 34,
                "category": BugCategory.RACE_CONDITION,
                "severity": Severity.HIGH,
                "file": "workers/job_queue.py",
                "description": "Result stored in _result_cache without acquiring _cache_lock"
            },
            {
                "line": 44,
                "category": BugCategory.LOGIC_ERROR,
                "severity": Severity.MEDIUM,
                "file": "workers/job_queue.py",
                "description": "stop() never clears self.workers; calling start() again will double the worker threads"
            },
            {
                "line": 77,
                "category": BugCategory.MEMORY_LEAK,
                "severity": Severity.MEDIUM,
                "file": "workers/job_queue.py",
                "description": "schedule_recurring spins a daemon thread with no stop mechanism; repeated calls leak threads"
            },
            {
                "line": 97,
                "category": BugCategory.LOGIC_ERROR,
                "severity": Severity.MEDIUM,
                "file": "workers/job_queue.py",
                "description": "run_with_timeout marks timeout but worker thread continues executing; no actual cancellation"
            },
            {
                "line": 35,
                "category": BugCategory.RACE_CONDITION,
                "severity": Severity.MEDIUM,
                "file": "workers/cache.py",
                "description": "get_or_set has cache stampede: multiple threads can compute func() simultaneously"
            },
            {
                "line": 40,
                "category": BugCategory.LOGIC_ERROR,
                "severity": Severity.LOW,
                "file": "workers/cache.py",
                "description": "size() counts expired entries, giving a misleading cache size"
            },
        ],
        security_issues=[
            {
                "line": 23,
                "category": SecurityCategory.INSECURE_DESERIALIZATION,
                "severity": Severity.CRITICAL,
                "file": "workers/job_queue.py",
                "description": "pickle.loads() on data from Redis is insecure deserialization; if Redis is compromised, attacker gets RCE"
            },
        ],
        correct_reviewer=ReviewerRole.SENIOR,
        should_approve=False,
        quality_comments=[
            "pickle deserialization", "race condition", "cache lock", "thread leak",
            "stampede", "worker cleanup", "timeout cancellation"
        ],
    ),
    difficulty="hard",
)


HARD_PR_2 = AnnotatedPR(
    pr=PullRequest(
        pr_id="PR-302",
        title="Multi-tenant data isolation layer",
        description="Adds tenant context middleware and query filtering to enforce data isolation between tenants in our SaaS platform.",
        author="senior_dev_2",
        files=[
            FileDiff(
                filename="middleware/tenant.ts",
                language="typescript",
                patch='''\
--- a/middleware/tenant.ts
+++ b/middleware/tenant.ts
@@ -0,0 +1,95 @@
+import { Request, Response, NextFunction } from 'express';
+import { getDB } from '../db';
+
+// Global mutable tenant context — NOT safe for async environments
+let currentTenantId: string | null = null;
+
+export function tenantMiddleware(req: Request, res: Response, next: NextFunction) {
+    const tenantId = req.headers['x-tenant-id'] as string;
+    if (!tenantId) {
+        return res.status(400).json({ error: 'Missing tenant ID' });
+    }
+    // BUG: setting a module-level variable in async Node.js is a race condition
+    // request A sets currentTenantId, then awaits DB; request B overwrites it
+    currentTenantId = tenantId;
+    next();
+}
+
+export function getCurrentTenantId(): string {
+    return currentTenantId!;  // BUG: can return null after tenantId is cleared
+}
+
+// Applies tenant filter to any query
+export async function tenantQuery(table: string, filters: Record<string, any>) {
+    const db = getDB();
+    const tenantId = getCurrentTenantId();
+
+    // Build WHERE clause from filters
+    const conditions = Object.entries(filters)
+        .map(([k, v]) => `${k} = '${v}'`)  // VULN: SQL injection via filter keys/values
+        .join(' AND ');
+
+    const query = conditions
+        ? `SELECT * FROM ${table} WHERE tenant_id = '${tenantId}' AND ${conditions}`
+        : `SELECT * FROM ${table} WHERE tenant_id = '${tenantId}'`;
+
+    return db.query(query);
+}
+
+export async function updateTenantRecord(
+    table: string,
+    id: string,
+    data: Record<string, any>
+) {
+    const db = getDB();
+    const tenantId = getCurrentTenantId();
+
+    // BUG: no validation that id belongs to current tenant before updating
+    // Tenant A can update Tenant B's records by guessing IDs
+    const updates = Object.entries(data)
+        .map(([k, v]) => `${k} = '${v}'`)
+        .join(', ');
+
+    return db.query(
+        `UPDATE ${table} SET ${updates} WHERE id = '${id}'`
+        // Missing: AND tenant_id = '${tenantId}'
+    );
+}
+
+export async function deleteTenantRecord(table: string, id: string) {
+    const db = getDB();
+    // VULN: no tenant check — any authenticated user can delete any record
+    return db.query(`DELETE FROM ${table} WHERE id = '${id}'`);
+}
+
+export async function getTenantConfig(tenantId: string) {
+    const db = getDB();
+    // Fetch config including API keys and feature flags
+    const config = await db.query(
+        `SELECT * FROM tenant_config WHERE tenant_id = '${tenantId}'`
+    );
+    // Return full config object including secrets — VULN: over-exposure
+    return config[0];
+}
+
+export function validateTenantAccess(requestTenantId: string, resourceTenantId: string) {
+    // VULN: comparison is case-sensitive; 'TenantA' !== 'tenanta' bypass
+    return requestTenantId === resourceTenantId;
+}
''',
                additions=95,
                deletions=0,
            ),
        ],
        language="typescript",
        total_additions=95,
        total_deletions=0,
    ),
    ground_truth=GroundTruth(
        bugs=[
            {
                "line": 13,
                "category": BugCategory.RACE_CONDITION,
                "severity": Severity.CRITICAL,
                "file": "middleware/tenant.ts",
                "description": "Module-level mutable currentTenantId causes cross-request tenant data leakage in async Node.js; use AsyncLocalStorage"
            },
            {
                "line": 19,
                "category": BugCategory.NULL_POINTER,
                "severity": Severity.HIGH,
                "file": "middleware/tenant.ts",
                "description": "getCurrentTenantId() returns null! which will crash if called outside tenant middleware context"
            },
            {
                "line": 43,
                "category": BugCategory.LOGIC_ERROR,
                "severity": Severity.CRITICAL,
                "file": "middleware/tenant.ts",
                "description": "updateTenantRecord does not filter by tenant_id; Tenant A can update Tenant B's records by guessing record IDs"
            },
        ],
        security_issues=[
            {
                "line": 28,
                "category": SecurityCategory.SQL_INJECTION,
                "severity": Severity.CRITICAL,
                "file": "middleware/tenant.ts",
                "description": "Filter keys and values are interpolated directly into SQL; attacker controls column names and values"
            },
            {
                "line": 55,
                "category": SecurityCategory.BROKEN_AUTH,
                "severity": Severity.CRITICAL,
                "file": "middleware/tenant.ts",
                "description": "deleteTenantRecord has no tenant_id check; any authenticated user can delete records across tenants"
            },
            {
                "line": 62,
                "category": SecurityCategory.SENSITIVE_DATA_EXPOSURE,
                "severity": Severity.HIGH,
                "file": "middleware/tenant.ts",
                "description": "getTenantConfig returns full config row including API keys and secrets to caller"
            },
        ],
        correct_reviewer=ReviewerRole.SECURITY,
        should_approve=False,
        quality_comments=[
            "asynclocalstorage", "tenant isolation", "sql injection", "race condition",
            "missing tenant filter", "data exposure", "multi-tenancy"
        ],
    ),
    difficulty="hard",
)


# ═══════════════════════════════════════════════════════════════════════════════
# Task → PR Mapping
# ═══════════════════════════════════════════════════════════════════════════════

TASK_PR_MAP: dict[str, list[AnnotatedPR]] = {
    "bug_detection":    [EASY_PR_1, EASY_PR_2],
    "security_audit":   [MEDIUM_PR_1, MEDIUM_PR_2],
    "full_review":      [HARD_PR_1, HARD_PR_2],
}
