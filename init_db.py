from models import create_database, create_tables, insert_sample_data

if __name__ == '__main__':
    create_database()
    create_tables()
    insert_sample_data()
    print("Database initialized with sample data.")