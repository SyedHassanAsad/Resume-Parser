from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
import spacy
import fitz  # PyMuPDF
import firebase_admin
from firebase_admin import credentials, firestore
import re
import csv

app = FastAPI()

# Add CORS middleware if React and FastAPI are running on different origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update this with the appropriate frontend domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Firebase Admin SDK
cred = credentials.Certificate("/Users/hassanjafri/Documents/Resume parser/smarthire-99e8f-firebase-adminsdk-gi62l-55bbf10c12.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# Load the spaCy model
nlp = spacy.load('en_core_web_sm')

# ----------------------------------Load Keywords from CSV-------------------------------
def load_keywords(file_path):
    with open(file_path, 'r') as file:
        reader = csv.reader(file)
        return set(row[0] for row in reader)

# ----------------------------------Extract Resume Info from PDF-------------------------------
def extract_resume_info_from_pdf(uploaded_file):
    doc = fitz.open(stream=uploaded_file.file.read(), filetype="pdf")
    text = ""
    for page_num in range(doc.page_count):
        page = doc[page_num]
        text += page.get_text()
    return nlp(text)

# ----------------------------------Extract Name----------------------------------
def extract_name(doc):
    for ent in doc.ents:
        if ent.label_ == 'PERSON':
            names = ent.text.split()
            if len(names) >= 2 and names[0].istitle() and names[1].istitle():
                return names[0], ' '.join(names[1:])
    return "", ""

# ----------------------------------Extract Email---------------------------------
def extract_email(doc):
    matcher = spacy.matcher.Matcher(nlp.vocab)
    email_pattern = [{'LIKE_EMAIL': True}]
    matcher.add('EMAIL', [email_pattern])

    matches = matcher(doc)
    for match_id, start, end in matches:
        if match_id == nlp.vocab.strings['EMAIL']:
            return doc[start:end].text
    return ""

# ----------------------------------Extract Phone Number---------------------------------
def extract_contact_number_from_resume(doc):
    text = doc.text  # Extract text from SpaCy doc object
    pattern = r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
    match = re.search(pattern, text)
    if match:
        return match.group()
    return ""

# ----------------------------------Extract Education---------------------------------
def extract_education_from_resume(doc):
    universities = []
    for entity in doc.ents:
        if entity.label_ == "ORG" and ("university" in entity.text.lower() or "college" in entity.text.lower()):
            universities.append(entity.text)
    return universities

# ----------------------------------Extract Experience---------------------------------
def extract_experience(doc):
    senior_keywords = ['lead', 'manage', 'direct', 'oversee', 'supervise']
    for token in doc:
        if token.pos_ == 'VERB' and token.lemma_.lower() in senior_keywords:
            return "Senior"
    return "Entry Level"

# ----------------------------------Extract Skills Using Keywords from CSV-------------------------------
def extract_skills(doc, keywords):
    skills = []
    for token in doc:
        if token.text.lower() in keywords:
            skills.append(token.text)
    return skills

# ----------------------------------Save Resume to Firestore-------------------------------
def save_resume_to_firestore(user_id, resume_data):
    resume_ref = db.collection('users').document(user_id).collection('ResumeDetails').document('resume')
    resume_ref.set(resume_data)
    print(f"Resume details saved for user: {user_id}")

# ----------------------------------API Route to Upload Resume-------------------------------
@app.post("/upload_resume")
async def upload_resume(file: UploadFile = File(...), user_id: str = Form(...)):
    doc = extract_resume_info_from_pdf(file)

    first_name, last_name = extract_name(doc)
    email = extract_email(doc)
    phone = extract_contact_number_from_resume(doc)
    education = extract_education_from_resume(doc)
    experience_level = extract_experience(doc)

    # Load skills keywords from CSV
    skills_keywords = load_keywords("/Users/hassanjafri/Documents/Resume parser/newSkills.csv")  # Adjust the file path
    skills = extract_skills(doc, skills_keywords)

    # Prepare resume data
    resume_data = {
        "First Name": first_name,
        "Last Name": last_name,
        "Email": email,
        "Phone Number": phone,
        "Education": education,
        "Experience Level": experience_level,
        "Skills": skills
    }

    # Save to Firestore
    save_resume_to_firestore(user_id, resume_data)

    return {"message": "Resume uploaded successfully", "data": resume_data}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)