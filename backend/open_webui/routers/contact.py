from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import uuid

router = APIRouter()

class Contact(BaseModel):
    first_name: str
    last_name: str
    company: str
    position: str
    email: str
    phone: str
    message: str

@router.post("/contact")
async def create_contact(contact: Contact):

    # Check if data is valid
    if not contact.first_name or not contact.last_name or not contact.email or not contact.message:
        raise HTTPException(status_code=400, detail="First Name, Last Name, Email and Message are required")

    # Write all data to file
    with open(f"/inbox/{contact.last_name}_{contact.first_name}_{uuid.uuid4()}.msg", "w") as f:
        f.write(f"First Name: {contact.first_name}\n")
        f.write(f"Last Name: {contact.last_name}\n")
        f.write(f"Company: {contact.company}\n")
        f.write(f"Position: {contact.position}\n")
        f.write(f"Email: {contact.email}\n")
        f.write(f"Phone: {contact.phone}\n")
        f.write(f"Message: {contact.message}\n")
        f.write("\n")

    return {"message": "Contact form submitted successfully", "contact": contact}