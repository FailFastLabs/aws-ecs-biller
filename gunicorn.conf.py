import multiprocessing

# Server socket
bind = "0.0.0.0:8000"

# Workers
workers = int(multiprocessing.cpu_count() * 2 + 1)
worker_class = "sync"
threads = 1
timeout = 120
keepalive = 5

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sµs'

# Process naming
proc_name = "aws-ecs-biller"

# Lifecycle
preload_app = True
max_requests = 1000
max_requests_jitter = 100
