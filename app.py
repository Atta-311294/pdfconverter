from flask import Flask, request, send_file, jsonify, after_this_request
from pdf2docx import Converter
import pdfplumber
import os
import threading
import urllib.parse
from docx import Document

app = Flask(__name__)

# Set up your folders
UPLOAD_FOLDER = "/home/attamalik311294/uploads"
CONVERTED_FOLDER = "/home/attamalik311294/converted_files"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["CONVERTED_FOLDER"] = CONVERTED_FOLDER

# Ensure folders exist
if not os.path.exists(app.config["UPLOAD_FOLDER"]):
    os.makedirs(app.config["UPLOAD_FOLDER"])
if not os.path.exists(app.config["CONVERTED_FOLDER"]):
    os.makedirs(app.config["CONVERTED_FOLDER"])


def extract_text_from_pdf(pdf_path):
    """Extract text from PDF using pdfplumber for complex PDFs."""
    try:
        text_content = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text_content += page.extract_text() or ""
        return text_content
    except Exception as e:
        raise Exception(f"Text extraction failed: {str(e)}")

def schedule_file_removal(file_path, delay=120):
    """Schedule file removal after `delay` seconds."""
    def remove_file():
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"File {file_path} deleted after timeout.")
            except Exception as e:
                print(f"Error deleting file: {str(e)}")

    timer = threading.Timer(delay, remove_file)
    timer.start()

@app.route("/pdf2docxconvert", methods=["POST"])
def convert_pdf_to_docx():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    if file and file.filename.lower().endswith(".pdf"):
        filename = file.filename
        upload_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(upload_path)

        try:
            # Convert the PDF to DOCX
            docx_filename = filename.replace(".pdf", ".docx")
            converted_path = os.path.join(CONVERTED_FOLDER, docx_filename)

            # Attempt pdf2docx conversion
            cv = Converter(upload_path)
            cv.convert(converted_path, start=0, end=None)
            cv.close()

            # Schedule file deletion in 2 minutes
            schedule_file_removal(converted_path, delay=120)

            # Check if DOCX is valid
            if os.path.exists(converted_path) and os.path.getsize(converted_path) > 0:
                return jsonify(
                    {
                        "message": "Conversion successful",
                        "converted_file": docx_filename,
                    }
                )
            else:
                raise Exception("Converted DOCX file is empty or invalid.")

        except Exception as e:
            # If pdf2docx fails, attempt text extraction using pdfplumber
            try:
                text_content = extract_text_from_pdf(upload_path)
                if text_content:
                    temp_docx_path = os.path.join(CONVERTED_FOLDER, docx_filename)
                    doc = Document()
                    doc.add_paragraph(text_content)
                    doc.save(temp_docx_path)
                    return jsonify(
                        {
                            "message": "Text extracted successfully",
                            "converted_file": docx_filename,
                        }
                    )
                else:
                    return (
                        jsonify({"error": "Text extraction yielded no content."}),
                        500,
                    )
            except Exception as extraction_error:
                return (
                    jsonify({"error": f"Conversion failed: {str(extraction_error)}"}),
                    500,
                )

        finally:
            # Clean up uploaded file
            if os.path.exists(upload_path):
                os.remove(upload_path)
    else:
        return jsonify({"error": "Invalid file type, only PDF is supported"}), 400

@app.route("/pdf2docxconverted/<filename>", methods=["GET"])
def get_converted_file_docx(filename):
    # Decode the filename from URL encoding
    decoded_filename = urllib.parse.unquote(filename)
    file_path = os.path.join(CONVERTED_FOLDER, decoded_filename)

    if os.path.exists(file_path):
        try:
            # Determine MIME type based on file extension
            if decoded_filename.endswith(".docx"):
                mimetype = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            elif decoded_filename.endswith(".pdf"):
                mimetype = "application/pdf"
            else:
                return jsonify({"error": "Unsupported file type"}), 400

            # Send the file with the original filename in the Content-Disposition header
            response = send_file(
                file_path,
                as_attachment=True,
                mimetype=mimetype,
                download_name=decoded_filename,  # Preserve the original filename
            )

            # Define the after request removal function
            @after_this_request
            def remove_file(response):
                try:
                    os.remove(file_path)  # Delete the file after sending it
                    print(f"File {file_path} deleted after sending.")
                except Exception as e:
                    print(f"Error deleting file: {str(e)}")
                return response

            return response

        except Exception as e:
            return jsonify({"error": f"Failed to send file: {str(e)}"}), 500
    else:
        return jsonify({"error": "File not found"}), 404

@app.route("/cleanup", methods=["DELETE"])
def cleanup_files():
    for file in os.listdir(CONVERTED_FOLDER):
        os.remove(os.path.join(CONVERTED_FOLDER, file))
    return jsonify({"message": "All converted files deleted."})



if __name__ == "__main__":
    app.run()
