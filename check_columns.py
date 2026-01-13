import sqlite3

# Connect to your database
conn = sqlite3.connect("data.db")
c = conn.cursor()

# Get all columns in 'customers' table
c.execute("PRAGMA table_info(customers)")
columns = c.fetchall()

print("Columns in 'customers' table:")
for col in columns:
    print(col[1])  # column name

conn.close()
