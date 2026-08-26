from groq import Groq
import json
import io
import os
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

LEVEL_GUIDANCE = {
    'entry': (
        "This is for an entry-level candidate. Emphasize education, internships, "
        "academic projects, and transferable skills. Frame limited experience as "
        "eagerness to learn and strong foundational ability rather than a weakness."
    ),
    'mid': (
        "This is for a mid-level candidate. Emphasize a solid track record of "
        "delivering results, growing scope of responsibility, and concrete, "
        "measurable achievements from recent roles."
    ),
    'senior': (
        "This is for a senior-level candidate. Emphasize technical or functional "
        "leadership, ownership of complex problems, mentoring others, and "
        "measurable impact beyond individual tasks."
    ),
    'executive': (
        "This is for an executive-level candidate. Emphasize strategic vision, "
        "organizational and business impact, stakeholder and P&L responsibility, "
        "and outcomes at a company-wide or market level rather than task-level detail."
    ),
}


def get_level_guidance(level):
    return LEVEL_GUIDANCE.get(level, LEVEL_GUIDANCE['mid'])


def analyze_cv(cv_text, job_description):
    prompt = f"""
    You are an expert CV/Resume analyst with a degree from harvard and you are highly regarded and recommeneded. Analyze the following CV against the job description and return a JSON response only, no extra text.

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
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )

    result = response.choices[0].message.content.strip()

    if result.startswith("```"):
        result = result.split("```")[1]
        if result.startswith("json"):
            result = result[4:]

    return json.loads(result.strip())


def rewrite_cv(cv_text, job_description, matched_skills, missing_skills, improvement_tips, level='mid'):
    prompt = f"""
    You are an expert CV writer with a degree from harvard and you are highly regarded and recommeneded. Rewrite the following CV to better match the job description and make sure it's not generic.

    Original CV:
    {cv_text}

    Job Description:
    {job_description}

    Analysis Insights:
    - Matched Skills: {matched_skills}
    - Missing Skills: {missing_skills}
    - Improvement Tips: {improvement_tips}

    Seniority Level:
    {get_level_guidance(level)}

    Instructions:
    - Keep all real experience and facts from the original CV
    - Rewrite and restructure to highlight relevant skills
    - Naturally incorporate missing skills only if they can be inferred from experience
    - Use strong action verbs and quantifiable achievements
    - Return the rewritten CV as plain text only, no extra commentary
    """

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
    )

    return response.choices[0].message.content.strip()


def generate_cover_letter(cv_text, job_description, matched_skills, improvement_tips, level='mid'):
    prompt = f"""
    You are an expert cover letter writer with a degree from harvard and you are highly regarded and recommeneded. Write a professional cover letter based on the CV and job description below and make sure it's not generic.

    CV:
    {cv_text}

    Job Description:
    {job_description}

    Analysis Insights:
    - Matched Skills: {matched_skills}
    - Improvement Tips: {improvement_tips}

    Seniority Level:
    {get_level_guidance(level)}

    Instructions:
    - Write a compelling, professional cover letter
    - Keep it to 3-4 paragraphs
    - Opening: express interest and strongest qualification
    - Middle: highlight matched skills with specific examples from CV
    - Closing: confident call to action
    - Do not use generic phrases like "I am writing to apply"
    - Return plain text only, no extra commentary
    """

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
    )

    return response.choices[0].message.content.strip()


def sanitize_text(text):
    """Replace Unicode typography that ReportLab's base font can't render
    (renders as black boxes) with plain ASCII equivalents."""
    if not text:
        return text

    replacements = {
        '\u2013': '-',   # en dash
        '\u2014': '-',   # em dash
        '\u2018': "'",   # left single quote
        '\u2019': "'",   # right single quote
        '\u201c': '"',   # left double quote
        '\u201d': '"',   # right double quote
        '\u2022': '-',   # bullet
        '\u2026': '...', # ellipsis
        '\u00a0': ' ',   # non-breaking space
        '\u2212': '-',   # minus sign
        '\u2192': '->',  # right arrow
        '\u2705': '',    # check mark emoji
        '\u2713': '',    # check mark
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)

    # Fallback: strip any remaining character the base font can't encode,
    # so a stray Unicode symbol never turns into a black box again.
    text = text.encode('latin-1', errors='ignore').decode('latin-1')
    return text


def generate_cv_pdf(rewritten_cv_text, user_full_name):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.units import inch
    from reportlab.lib import colors

    rewritten_cv_text = sanitize_text(rewritten_cv_text)
    user_full_name = sanitize_text(user_full_name)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=inch, leftMargin=inch, topMargin=inch, bottomMargin=inch)
    styles = getSampleStyleSheet()

    name_style = ParagraphStyle('NameStyle', parent=styles['Title'], fontSize=20, textColor=colors.HexColor('#1a1a2e'), spaceAfter=6)
    normal_style = ParagraphStyle('NormalStyle', parent=styles['Normal'], fontSize=11, leading=16, spaceAfter=6)
    heading_style = ParagraphStyle('HeadingStyle', parent=styles['Heading2'], fontSize=13, textColor=colors.HexColor('#1a1a2e'), spaceBefore=12, spaceAfter=4)

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


def generate_cover_letter_pdf(cover_letter_text, user_full_name):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.units import inch
    from reportlab.lib import colors

    cover_letter_text = sanitize_text(cover_letter_text)
    user_full_name = sanitize_text(user_full_name)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=inch, leftMargin=inch, topMargin=inch, bottomMargin=inch)
    styles = getSampleStyleSheet()

    name_style = ParagraphStyle('NameStyle', parent=styles['Title'], fontSize=18, textColor=colors.HexColor('#1a1a2e'), spaceAfter=6)
    normal_style = ParagraphStyle('NormalStyle', parent=styles['Normal'], fontSize=11, leading=18, spaceAfter=8)

    story = []
    story.append(Paragraph(user_full_name, name_style))
    story.append(Paragraph("Cover Letter", ParagraphStyle('Sub', parent=styles['Normal'], fontSize=12, textColor=colors.HexColor('#666666'), spaceAfter=20)))
    story.append(Spacer(1, 0.2 * inch))

    for line in cover_letter_text.split('\n'):
        line = line.strip()
        if not line:
            story.append(Spacer(1, 0.1 * inch))
        else:
            story.append(Paragraph(line, normal_style))

    doc.build(story)
    buffer.seek(0)
    return buffer