import psycopg2

conn = psycopg2.connect('postgresql://postgres:123456@localhost:5432/postgres')
conn.autocommit = True
cur = conn.cursor()
try:
    cur.execute('DROP DATABASE iqac_worklog;')
    print('Dropped existing database')
except Exception as e:
    print(f'Note: {e}')
    
cur.execute('CREATE DATABASE iqac_worklog;')
print('Database created successfully!')
conn.close()
