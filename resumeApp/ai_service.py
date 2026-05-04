from groq import Groq
import json
import io
import os
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def analyze_cv(cv_text, job_description):
    prompt = f"""
    You are an expert CV/Resume analyst. Analyze the following CV against the job description and return a JSON response only, no extra text.

    CV:
    {cv_text}

    Job Description:
    {job_description}

    Return this exact JSON structure:
    {{
        "match_score": <integer between 0 and 100>,
        "matched_skills": "<comma separated list of matched skills>",
        "missing_skills": "<comma separated list of missing skills>",
        "improvement_tips": "<specific tips to improve the CV for this role>",
        "summary": "<2-3 sentence overall verdict>"
    }}

    Return JSON only, no markdown, no extra text.
    """

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )

    result = response.choices[0].message.content.strip()

    if result.startswith("```"):
        result = result.split("```")[1]
        if result.startswith("json"):
            result = result[4:]

    return json.loads(result.strip())


def rewrite_cv(cv_text, job_description, matched_skills, missing_skills, improvement_tips):
    prompt = f"""
    You are an expert CV writer. Rewrite the following CV to better match the job description.
    Use the analysis insights provided to improve the CV.

    Original CV:
    {cv_text}

    Job Description:
    {job_description}

    Analysis Insights:
    - Matched Skills: {matched_skills}
    - Missing Skills: {missing_skills}
    - Improvement Tips: {improvement_tips}

    Instructions:
    - Keep all real experience and facts from the original CV
    - Rewrite and restructure to highlight relevant skills
    - Naturally incorporate missing skills only if they can be inferred from experience
    - Use strong action verbs and quantifiable achievements
    - Return the rewritten CV as plain text only, no extra commentary
    """

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
    )

    return response.choices[0].message.content.strip()


def generate_cv_pdf(rewritten_cv_text, user_full_name):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.units import inch
    from reportlab.lib import colors

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=inch,
        leftMargin=inch,
        topMargin=inch,
        bottomMargin=inch
    )

    styles = getSampleStyleSheet()

    name_style = ParagraphStyle(
        'NameStyle',
        parent=styles['Title'],
        fontSize=20,
        textColor=colors.HexColor('#1a1a2e'),
        spaceAfter=6,
    )

    normal_style = ParagraphStyle(
        'NormalStyle',
        parent=styles['Normal'],
        fontSize=11,
        leading=16,
        spaceAfter=6,
    )

    heading_style = ParagraphStyle(
        'HeadingStyle',
        parent=styles['Heading2'],
        fontSize=13,
        textColor=colors.HexColor('#1a1a2e'),
        spaceBefore=12,
        spaceAfter=4,
    )

    story = []
    story.append(Paragraph(user_full_name, name_style))
    story.append(Spacer(1, 0.2 * inch))

    for line in rewritten_cv_text.split('\n'):
        line = line.strip()
        if not line:
            story.append(Spacer(1, 0.1 * inch))
        elif line.isupper() or line.endswith(':'):
            story.append(Paragraph(line, heading_style))
        else:
            story.append(Paragraph(line, normal_style))

    doc.build(story)
    buffer.seek(0)
    return buffer