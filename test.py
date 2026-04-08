# import redis
# from routes.customer import get_supabase
from werkzeug.security import generate_password_hash
# r = redis.from_url(
#     "rediss://default:gQAAAAAAARi6AAIncDJkYWYwMTY1ZGE5NjU0Zjk3OGUxMDc5MDA0NzVhMjVjYnAyNzE4NjY@pleasant-cicada-71866.upstash.io:6379",
#     decode_responses=True
# )
# print(r.ping())  # 201 True

# supabase = get_supabase()
# # Temporary check
# users = supabase.table('profiles').select('role').execute()
# roles = set([user['role'] for user in users.data])
# print(f"Existing roles sa database: {roles}")

# Password test
print(generate_password_hash("Masong0808#")) 
