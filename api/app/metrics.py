from prometheus_client import Counter, Gauge, Histogram

REQUESTS = Counter("biometric_requests_total", "API requests", ["route", "status"])
VERIFY = Counter("biometric_verifications_total", "Verification decisions", ["decision"])
LATENCY = Histogram("biometric_verification_seconds", "Verification latency")
PEOPLE = Gauge("biometric_people_total", "Enrolled people")
MODEL_INFO = Gauge("biometric_model_info", "Loaded model metadata", ["version", "backend"])

