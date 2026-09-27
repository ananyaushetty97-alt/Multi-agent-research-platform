# test_cache_direct.py
from memory import check_cache, save_to_ltm

topic = "direct cache test topic"

print("Before saving:", check_cache(topic))

save_to_ltm("This is a test report for caching.", topic=topic)

print("After saving:", check_cache(topic))