from openai import OpenAI
import json
import io
import os
import re
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

MODEL_NAME = "gpt-5.6-luna"

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
    system_msg = (
        "You are a senior CV/resume analyst. You assess CVs against job "
        "descriptions with precision and give concrete, actionable feedback."
    )
    prompt = f"""Analyze this CV against the job description.

CV:
{cv_text}

Job Description:
{job_description}

Return this exact JSON structure:
{{
    "match_score": <integer 0-100>,
    "matched_skills": "<comma separated list>",
    "missing_skills": "<comma separated list>",
    "improvement_tips": "<specific tips for this role>",
    "summary": "<2-3 sentence verdict>"
}}"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ],
        reasoning_effort="medium",
        max_completion_tokens=600,
        response_format={"type": "json_object"},
    )

    result = response.choices[0].message.content.strip()

    # Safety net in case the model still wraps output in a code fence
    if result.startswith("```"):
        result = result.split("```")[1]
        if result.startswith("json"):
            result = result[4:]

    return json.loads(result.strip())


def rewrite_cv(cv_text, job_description, matched_skills, missing_skills, improvement_tips, level='mid'):
    system_msg = (
        "You are a senior professional CV writer. You rewrite CVs to be "
        "sharp, specific, and tailored, never generic. You always follow "
        "the exact tag format given to you, with no deviation and no "
        "extra commentary outside the tags."
    )
    prompt = f"""Rewrite this CV to better match the job description.

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

Content instructions:
- Keep all real experience and facts from the original CV
- Rewrite and restructure to highlight relevant skills
- Naturally incorporate missing skills only if inferable from experience
- Use strong action verbs and quantifiable achievements
- Do NOT repeat the candidate's name anywhere in the output — it is added separately as the document title

Format instructions — output MUST use exactly this tag structure, with no markdown, no extra headings, and no text outside the tags:

Line 1: the candidate's professional title/role line (e.g. "Data Analyst | Backend Developer")
Line 2: contact line (email | phone | location | LinkedIn/portfolio if present in the original CV)
(blank line)
[EYEBROW]PROFILE[/EYEBROW]
[HEADING]Professional Summary[/HEADING]
<one paragraph of plain text>
(blank line)
[EYEBROW]TOOLKIT[/EYEBROW]
[HEADING]Technical Skills[/HEADING]
[SKILL]<category name>|<comma-separated list of skills in that category>[/SKILL]
(one [SKILL] line per category, 3-6 categories)
(blank line)
[EYEBROW]CAREER[/EYEBROW]
[HEADING]Work Experience[/HEADING]
[JOB]<job title>|<date range>|<company name>[/JOB]
- <bullet achievement>
- <bullet achievement>
(repeat [JOB] + bullets for each role, most recent first)
(blank line)
[EYEBROW]PORTFOLIO[/EYEBROW]
[HEADING]Notable Projects[/HEADING]
[PROJECT]<project name>[/PROJECT]
<one paragraph describing it>
(repeat for each notable project, omit this whole section if the original CV has none)
(blank line)
[EYEBROW]QUALIFICATIONS[/EYEBROW]
[HEADING]Education and Certification[/HEADING]
[JOB]<degree/certificate name>|<date range>|<institution>[/JOB]
<one line of detail if relevant>

Return only the tagged content above, nothing else."""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ],
        reasoning_effort="medium",
        max_completion_tokens=4000,
    )

    result = response.choices[0].message.content.strip()
    if not result:
        raise ValueError(
            f"rewrite_cv returned empty output (finish_reason={response.choices[0].finish_reason}). "
            "Likely truncated by max_completion_tokens before visible text was produced."
        )
    return result


def rebuild_cv(cv_text, level='mid'):
    """Rebuild a CV into a polished, professional version with no specific
    job description to tailor against — general presentation upgrade only."""
    system_msg = (
        "You are a senior professional CV writer. You take outdated, messy, "
        "or poorly formatted CVs and rebuild them into sharp, professional "
        "documents, never generic. You always follow the exact tag format "
        "given to you, with no deviation and no extra commentary outside "
        "the tags."
    )
    prompt = f"""Rebuild this CV into a polished, professional version. There is no
specific job description to tailor it against — focus on clarity, strong
action verbs, quantifiable achievements, and consistent professional
presentation throughout.

Original CV:
{cv_text}

Seniority Level:
{get_level_guidance(level)}

Content instructions:
- Keep all real experience and facts from the original CV — never invent employers, dates, or achievements
- Rewrite weak or vague phrasing into specific, results-oriented language
- Reorganize for clarity and logical flow if the original is poorly structured
- Use strong action verbs and quantifiable achievements wherever the original supports it
- Do NOT repeat the candidate's name anywhere in the output — it is added separately as the document title

Format instructions — output MUST use exactly this tag structure, with no markdown, no extra headings, and no text outside the tags:

Line 1: the candidate's professional title/role line (e.g. "Data Analyst | Backend Developer")
Line 2: contact line (email | phone | location | LinkedIn/portfolio if present in the original CV)
(blank line)
[EYEBROW]PROFILE[/EYEBROW]
[HEADING]Professional Summary[/HEADING]
<one paragraph of plain text>
(blank line)
[EYEBROW]TOOLKIT[/EYEBROW]
[HEADING]Technical Skills[/HEADING]
[SKILL]<category name>|<comma-separated list of skills in that category>[/SKILL]
(one [SKILL] line per category, 3-6 categories)
(blank line)
[EYEBROW]CAREER[/EYEBROW]
[HEADING]Work Experience[/HEADING]
[JOB]<job title>|<date range>|<company name>[/JOB]
- <bullet achievement>
- <bullet achievement>
(repeat [JOB] + bullets for each role, most recent first)
(blank line)
[EYEBROW]PORTFOLIO[/EYEBROW]
[HEADING]Notable Projects[/HEADING]
[PROJECT]<project name>[/PROJECT]
<one paragraph describing it>
(repeat for each notable project, omit this whole section if the original CV has none)
(blank line)
[EYEBROW]QUALIFICATIONS[/EYEBROW]
[HEADING]Education and Certification[/HEADING]
[JOB]<degree/certificate name>|<date range>|<institution>[/JOB]
<one line of detail if relevant>

Return only the tagged content above, nothing else."""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ],
        reasoning_effort="medium",
        max_completion_tokens=4000,
    )

    result = response.choices[0].message.content.strip()
    if not result:
        raise ValueError(
            f"rebuild_cv returned empty output (finish_reason={response.choices[0].finish_reason}). "
            "Likely truncated by max_completion_tokens before visible text was produced."
        )
    return result


def create_cv_from_scratch(data, level='mid', reference_cv_text=None):
    """Builds a brand-new CV from structured wizard input. `data` is a dict
    with keys matching the CVCreation model: full_name, email, phone,
    location, linkedin, portfolio, professional_summary, work_experience,
    education, skills, projects, certifications, achievements."""
    system_msg = (
        "You are a senior professional CV writer. You build brand-new, "
        "polished CVs from structured candidate information, never generic. "
        "You always follow the exact tag format given to you, with no "
        "deviation and no extra commentary outside the tags."
    )

    def format_list(items, formatter):
        return "\n".join(formatter(i) for i in items) if items else "(none provided)"

    work_block = format_list(
        data.get('work_experience', []),
        lambda j: f"- {j.get('title', '')} at {j.get('company', '')} "
                  f"({j.get('start_date', '')} - {j.get('end_date', '')}, {j.get('location', '')}): "
                  + "; ".join(j.get('bullets', []))
    )
    education_block = format_list(
        data.get('education', []),
        lambda e: f"- {e.get('degree', '')}, {e.get('institution', '')} "
                  f"({e.get('start_date', '')} - {e.get('end_date', '')}): {e.get('details', '')}"
    )
    skills_block = format_list(
        data.get('skills', []),
        lambda s: f"- {s.get('category', '')}: {', '.join(s.get('items', []))}"
    )
    projects_block = format_list(
        data.get('projects', []),
        lambda p: f"- {p.get('name', '')}: {p.get('description', '')}"
    )
    certifications_block = format_list(
        data.get('certifications', []),
        lambda c: f"- {c.get('name', '')} ({c.get('issuer', '')}, {c.get('date', '')})"
    )
    achievements_block = format_list(data.get('achievements', []), lambda a: f"- {a}")

    reference_section = ""
    if reference_cv_text:
        reference_section = f"""
The candidate also provided an existing CV for style/content reference only.
Use it only to understand tone and phrasing style — do not copy it verbatim,
and do not pull in any facts, dates, or achievements from it that aren't
already supported by the structured information below:

{reference_cv_text}
"""

    prompt = f"""Build a brand-new, polished, professional CV from this candidate's information.

Personal Details:
Name: {data.get('full_name', '')}
Email: {data.get('email', '')}
Phone: {data.get('phone', '')}
Location: {data.get('location', '')}
LinkedIn: {data.get('linkedin', '')}
Portfolio: {data.get('portfolio', '')}

Professional Summary (candidate's draft — polish or rewrite as needed; if empty, write one from the rest of the information below):
{data.get('professional_summary') or '(not provided — write one from the details below)'}

Work Experience:
{work_block}

Education:
{education_block}

Skills:
{skills_block}

Projects:
{projects_block}

Certifications:
{certifications_block}

Achievements:
{achievements_block}
{reference_section}
Seniority Level:
{get_level_guidance(level)}

Content instructions:
- Use only the facts given above — never invent employers, dates, or achievements
- Turn plain descriptions into strong action-verb, results-oriented bullets
- Write a compelling professional summary if none was provided
- Do NOT repeat the candidate's name anywhere in the output — it is added separately as the document title

Format instructions — output MUST use exactly this tag structure, with no markdown, no extra headings, and no text outside the tags:

Line 1: the candidate's professional title/role line
Line 2: contact line (email | phone | location | LinkedIn/portfolio if provided)
(blank line)
[EYEBROW]PROFILE[/EYEBROW]
[HEADING]Professional Summary[/HEADING]
<one paragraph of plain text>
(blank line)
[EYEBROW]TOOLKIT[/EYEBROW]
[HEADING]Technical Skills[/HEADING]
[SKILL]<category name>|<comma-separated list of skills in that category>[/SKILL]
(one [SKILL] line per category)
(blank line)
[EYEBROW]CAREER[/EYEBROW]
[HEADING]Work Experience[/HEADING]
[JOB]<job title>|<date range>|<company name>[/JOB]
- <bullet achievement>
(repeat [JOB] + bullets for each role, most recent first; omit this whole section if no work experience was provided)
(blank line)
[EYEBROW]PORTFOLIO[/EYEBROW]
[HEADING]Notable Projects[/HEADING]
[PROJECT]<project name>[/PROJECT]
<one paragraph describing it>
(repeat for each project; omit this whole section if none were provided)
(blank line)
[EYEBROW]QUALIFICATIONS[/EYEBROW]
[HEADING]Education and Certification[/HEADING]
[JOB]<degree/certificate name>|<date range>|<institution>[/JOB]
<one line of detail if relevant>

Return only the tagged content above, nothing else."""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ],
        reasoning_effort="medium",
        max_completion_tokens=4000,
    )

    result = response.choices[0].message.content.strip()
    if not result:
        raise ValueError(
            f"create_cv_from_scratch returned empty output (finish_reason={response.choices[0].finish_reason}). "
            "Likely truncated by max_completion_tokens before visible text was produced."
        )
    return result


def generate_cover_letter(cv_text, job_description, matched_skills, improvement_tips, level='mid'):
    system_msg = (
        "You are a senior professional cover letter writer. You write "
        "compelling, specific cover letters that never sound generic."
    )
    prompt = f"""Write a professional cover letter based on this CV and job description.

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
- Keep it to 3-4 paragraphs
- Opening: express interest and strongest qualification
- Middle: highlight matched skills with specific examples from CV
- Closing: confident call to action
- Do not use generic phrases like "I am writing to apply"
- Return plain text only, no extra commentary"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ],
        reasoning_effort="medium",
        max_completion_tokens=1500,
    )

    result = response.choices[0].message.content.strip()
    if not result:
        raise ValueError(
            f"generate_cover_letter returned empty output (finish_reason={response.choices[0].finish_reason}). "
            "Likely truncated by max_completion_tokens before visible text was produced."
        )
    return result


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


EYEBROW_RE = re.compile(r'^\[EYEBROW\](.*?)\[/EYEBROW\]$')
HEADING_RE = re.compile(r'^\[HEADING\](.*?)\[/HEADING\]$')
SKILL_RE = re.compile(r'^\[SKILL\](.*?)\|(.*?)\[/SKILL\]$')
JOB_RE = re.compile(r'^\[JOB\](.*?)\|(.*?)\|(.*?)\[/JOB\]$')
PROJECT_RE = re.compile(r'^\[PROJECT\](.*?)\[/PROJECT\]$')


def generate_cv_pdf(rewritten_cv_text, user_full_name):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT

    rewritten_cv_text = sanitize_text(rewritten_cv_text)
    user_full_name = sanitize_text(user_full_name)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=0.55 * inch, leftMargin=0.55 * inch,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
    )
    styles = getSampleStyleSheet()
    content_width = A4[0] - 1.1 * inch

    name_style = ParagraphStyle('NameStyle', parent=styles['Title'], fontSize=17, textColor=colors.HexColor('#1a1a2e'), spaceAfter=1, leading=20)
    role_style = ParagraphStyle('RoleStyle', parent=styles['Normal'], fontSize=10.5, textColor=colors.HexColor('#333333'), spaceAfter=1)
    contact_style = ParagraphStyle('ContactStyle', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#555555'), spaceAfter=6)
    eyebrow_style = ParagraphStyle('EyebrowStyle', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#a07d2e'), spaceAfter=0, leading=10)
    heading_style = ParagraphStyle('HeadingStyle', parent=styles['Heading2'], fontSize=12.5, textColor=colors.HexColor('#1a1a2e'), spaceBefore=0, spaceAfter=4)
    normal_style = ParagraphStyle('NormalStyle', parent=styles['Normal'], fontSize=9.5, leading=12.5, spaceAfter=3, alignment=TA_LEFT)
    bullet_style = ParagraphStyle('BulletStyle', parent=normal_style, leftIndent=12, spaceAfter=2)
    project_style = ParagraphStyle('ProjectStyle', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#1a1a2e'), spaceBefore=4, spaceAfter=2)
    skill_label_style = ParagraphStyle('SkillLabelStyle', parent=normal_style, fontSize=9.5, textColor=colors.HexColor('#1a1a2e'))
    job_title_style = ParagraphStyle('JobTitleStyle', parent=normal_style, fontSize=10, spaceAfter=0)
    job_date_style = ParagraphStyle('JobDateStyle', parent=normal_style, fontSize=9, textColor=colors.HexColor('#666666'), alignment=TA_RIGHT, spaceAfter=0)
    job_company_style = ParagraphStyle('JobCompanyStyle', parent=normal_style, fontSize=9.5, textColor=colors.HexColor('#555555'), spaceAfter=3)

    lines = [ln.rstrip() for ln in rewritten_cv_text.split('\n')]
    has_tags = any('[EYEBROW]' in ln or '[HEADING]' in ln for ln in lines)

    story = []
    story.append(Paragraph(user_full_name, name_style))

    if not has_tags:
        # Fallback: model didn't follow the tag format this time. Render
        # with the same dense heuristic layout as before, so nothing breaks.
        story.append(Spacer(1, 0.08 * inch))
        prev_blank = True
        for line in lines:
            line = line.strip()
            if not line:
                if not prev_blank:
                    story.append(Spacer(1, 0.05 * inch))
                prev_blank = True
                continue
            prev_blank = False
            if line.isupper() or (line.endswith(':') and len(line) < 60):
                story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor('#c9c9c9'), spaceBefore=2, spaceAfter=2))
                story.append(Paragraph(line, heading_style))
            elif line.startswith(('-', '•', '*')):
                bullet_text = line.lstrip('-•* ').strip()
                story.append(Paragraph(f"&bull;&nbsp;&nbsp;{bullet_text}", bullet_style))
            else:
                story.append(Paragraph(line, normal_style))
        doc.build(story)
        buffer.seek(0)
        return buffer

    # Tag-based render: first two non-blank lines are role + contact.
    header_lines_consumed = 0
    idx = 0
    while idx < len(lines) and header_lines_consumed < 2:
        line = lines[idx].strip()
        idx += 1
        if not line:
            continue
        style = role_style if header_lines_consumed == 0 else contact_style
        story.append(Paragraph(line, style))
        header_lines_consumed += 1

    prev_blank = True
    for line in lines[idx:]:
        line = line.strip()
        if not line:
            if not prev_blank:
                story.append(Spacer(1, 0.06 * inch))
            prev_blank = True
            continue
        prev_blank = False

        m = EYEBROW_RE.match(line)
        if m:
            story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor('#c9c9c9'), spaceBefore=2, spaceAfter=1))
            story.append(Paragraph(m.group(1).strip(), eyebrow_style))
            continue

        m = HEADING_RE.match(line)
        if m:
            story.append(Paragraph(m.group(1).strip(), heading_style))
            continue

        m = SKILL_RE.match(line)
        if m:
            label, items = m.group(1).strip(), m.group(2).strip()
            row = Table(
                [[Paragraph(f"<b>{label}</b>", skill_label_style), Paragraph(items, normal_style)]],
                colWidths=[1.5 * inch, content_width - 1.5 * inch],
            )
            row.setStyle(TableStyle([
                ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            story.append(row)
            continue

        m = JOB_RE.match(line)
        if m:
            title, dates, company = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
            row = Table(
                [[Paragraph(f"<b>{title}</b>", job_title_style), Paragraph(dates, job_date_style)]],
                colWidths=[content_width - 1.6 * inch, 1.6 * inch],
            )
            row.setStyle(TableStyle([
                ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            story.append(row)
            story.append(Paragraph(company, job_company_style))
            continue

        m = PROJECT_RE.match(line)
        if m:
            story.append(Paragraph(f"<b>{m.group(1).strip()}</b>", project_style))
            continue

        if line.startswith(('-', '•', '*')):
            bullet_text = line.lstrip('-•* ').strip()
            story.append(Paragraph(f"&bull;&nbsp;&nbsp;{bullet_text}", bullet_style))
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