import os

# The brain refuses to start without a secret; give tests a dummy one before
# any application code is imported.
os.environ.setdefault("AI_ASSISTANT_SECRET", "test-secret")
