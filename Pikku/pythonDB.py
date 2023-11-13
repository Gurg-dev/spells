import os
import sqlite3
from flask import Flask, request, render_template, send_file, url_for
import zipfile

from flask_cors import CORS  # Allow requests from all origins (insecure, for testing)

app = Flask(__name__)
CORS(app)  # Allow requests from all origins (insecure, for testing)

UPLOAD_FOLDER = 'uploads'
DATABASE_FOLDER = 'databases'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'txt'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['DATABASE_FOLDER'] = DATABASE_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def create_image_zip(db_name, image_filenames, info):
    zip_path = os.path.join(app.config['DATABASE_FOLDER'], f'{db_name}.zip')

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Save text info to a text file within the zip
        text_filename = f'{db_name}_info.txt'
        with zipf.open(text_filename, 'w') as text_file:
            text_file.write(info.encode('utf-8'))

        # Add database file and images to the zip
        db_path = os.path.join(app.config['DATABASE_FOLDER'], f'{db_name}.sqlite')
        zipf.write(db_path, os.path.basename(db_path))
        for image_filename in image_filenames:
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
            zipf.write(image_path, os.path.basename(image_filename))

    return zip_path
try:
    @app.route('/search', methods=['GET'])
    def search():
        db_path = os.path.join(app.config['DATABASE_FOLDER'], 'your_database.sqlite')  # Replace with your actual database filename
        search_query = request.args.get('search_query')
        if search_query:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Check if the "data" table exists before querying it
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='data'")
            table_exists = cursor.fetchone()

            if table_exists:
                cursor.execute("SELECT * FROM data WHERE info LIKE ?", ('%' + search_query + '%',))
                query_results = cursor.fetchall()
                conn.close()

                # Rest of your code to prepare and return results
                # Prepare the results with image URLs
                results_with_images = []
                for result in query_results:
                    info, image_filenames = result[1], result[2].split(';')
                    image_urls = [url_for('get_image', db=result[0], filename=filename) for filename in image_filenames]
                    results_with_images.append((info, image_urls))

                return render_template('query_results.html', results=results_with_images)
            else:
                conn.close()
                return "The 'data' table does not exist."
        else:
            # Rest of your code
            print(f"Database path: {db_path}")
            print(query_results)
            return "Search query missing."
except Exception as e:
    print(f"An error occurred: {e}")


    
@app.route('/')
def index():
    return render_template('query_results.html')

database_counter = 1  # Initialize a counter to track database numbering

@app.route('/upload', methods=['POST'])
def upload_file():
    global database_counter  # Access the global counter

    if 'files[]' not in request.files or 'info' not in request.form:
        return "Missing file or information."

    files = request.files.getlist('files[]')
    info = request.form['info']

    db_name = f'database_{database_counter}'
    database_counter += 1  # Increment the counter for the next database

    db_path = os.path.join(app.config['DATABASE_FOLDER'], f'{db_name}.sqlite')

    # Save the uploaded image files
    image_filenames = []
    for file in files:
        if file.filename == '' or not allowed_file(file.filename):
            return "Invalid file type."
        image_filename = f'{db_name}_{len(image_filenames) + 1}.png'  # Save image as PNG
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
        file.save(image_path)
        image_filenames.append(image_filename)

    # Save the image filenames and info to the database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create the "data" table if it doesn't exist
    cursor.execute('''CREATE TABLE IF NOT EXISTS data (id INTEGER PRIMARY KEY, info TEXT, images TEXT)''')

    # Save the image filenames as a semicolon-separated string
    images_string = ';'.join(image_filenames)
    cursor.execute('INSERT INTO data (info, images) VALUES (?, ?)', (info, images_string))
    conn.commit()
    conn.close()

    # Create a zip archive containing images and text
    zip_path = create_image_zip(db_name, image_filenames, info)

    # Remove uploaded image files from the uploads folder
    for image_filename in image_filenames:
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
        os.remove(image_path)

    return "File(s) uploaded and database saved."


# ... (rest of your code)

@app.route('/query', methods=['GET'])
def query():
    search_query = request.args.get('search_query')

    if search_query:
        all_results = []  # To store results from all databases
        extracted_db_paths = []  # To track extracted database paths for cleanup

        # Loop through all database files in the DATABASE_FOLDER
        for filename in os.listdir(app.config['DATABASE_FOLDER']):
            if filename.endswith('.zip'):
                db_id = filename[:-4]  # Remove the ".zip" extension
                compressed_db_path = os.path.join(app.config['DATABASE_FOLDER'], filename)
                extracted_db_path = os.path.join(app.config['DATABASE_FOLDER'], f'{db_id}.sqlite')

                # Extract the database from the ZIP
                with zipfile.ZipFile(compressed_db_path, 'r') as zip_ref:
                    zip_ref.extract(f'{db_id}.sqlite', app.config['DATABASE_FOLDER'])

                extracted_db_paths.append(extracted_db_path)  # Track the extracted DB path

                try:
                    # Query the extracted database
                    conn = sqlite3.connect(extracted_db_path)
                    cursor = conn.cursor()
                    cursor.execute('SELECT * FROM data WHERE info LIKE ?', ('%' + search_query + '%',))
                    query_results = cursor.fetchall()

                    # Prepare the results with image URLs
                    results_with_images = []
                    for result in query_results:
                        info, image_filenames = result[1], result[2].split(';')
                        image_urls = [url_for('get_image', db=db_id, filename=filename) for filename in image_filenames]
                        results_with_images.append((info, image_urls))

                    all_results.extend(results_with_images)
                finally:
                    conn.close()  # Close the connection even if an exception occurs

        # Clean up: remove the extracted database files
        for extracted_db_path in extracted_db_paths:
            os.remove(extracted_db_path)

        return render_template('query_results.html', results=all_results)
    else:
        return "Search query missing."





@app.route('/get_image/<db>/<filename>')
def get_image(db, filename):
    compressed_db_path = os.path.join(app.config['DATABASE_FOLDER'], f'{db}.zip')

    # Extract the image from the ZIP and serve it
    with zipfile.ZipFile(compressed_db_path, 'r') as zip_ref:
        extracted_image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        with zip_ref.open(filename) as extracted_image:
            with open(extracted_image_path, 'wb') as f:
                f.write(extracted_image.read())

    return send_file(extracted_image_path)

# ... (rest of your code)


if __name__ == '__main__':
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    if not os.path.exists(DATABASE_FOLDER):
        os.makedirs(DATABASE_FOLDER)


    app.run(debug=True)
