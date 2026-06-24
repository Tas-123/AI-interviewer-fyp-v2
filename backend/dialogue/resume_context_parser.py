"""
Resume Context Parser — Extracts structured candidate data from resume text.

Provides deterministic keyword/pattern extraction without LLM dependency.
Used by the question selector to generate resume-conditioned questions.
"""

import re


# ── Known technology/tool keywords ──────────────────────────────
KNOWN_SKILLS = [
    "python", "javascript", "typescript", "java", "c++", "c#", "go",
    "rust", "ruby", "php", "swift", "kotlin", "scala", "r",
    "react", "angular", "vue", "next.js", "node.js", "express",
    "django", "flask", "fastapi", "spring", "rails",
    "sql", "postgresql", "postgres", "mysql", "mongodb", "redis",
    "elasticsearch", "dynamodb", "sqlite",
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform",
    "ci/cd", "jenkins", "github actions", "gitlab",
    "machine learning", "deep learning", "nlp", "computer vision",
    "tensorflow", "pytorch", "scikit-learn", "pandas", "numpy",
    "rest api", "graphql", "grpc", "microservices",
    "git", "linux", "agile", "scrum", "jira",
    "html", "css", "tailwind", "bootstrap",
]

KNOWN_ROLES = [
    "software engineer", "backend engineer", "frontend engineer",
    "full stack developer", "full-stack developer",
    "data scientist", "data engineer", "ml engineer",
    "devops engineer", "site reliability engineer", "sre",
    "product manager", "project manager", "tech lead",
    "engineering manager", "architect", "qa engineer",
    "mobile developer", "ios developer", "android developer",
]

# Experience pattern: "X years" or "X+ years"
EXPERIENCE_PATTERN = re.compile(
    r"(\d+)\+?\s*(?:years?|yrs?)\s*(?:of)?\s*(?:experience)?",
    re.IGNORECASE,
)


def parse_resume(resume_text: str) -> dict:
    """
    Extract structured candidate data from resume text.

    Args:
        resume_text: raw text content of the candidate's resume

    Returns:
        {
            "candidate_skills": [...],
            "candidate_tools": [...],
            "candidate_experience": "X years" or "not specified",
            "candidate_role": "detected role" or "not specified"
        }
    """
    if not resume_text or not isinstance(resume_text, str):
        return {
            "candidate_skills": [],
            "candidate_tools": [],
            "candidate_experience": "not specified",
            "candidate_role": "not specified",
        }

    text_lower = resume_text.lower()

    # ── Extract skills & tools ──────────────────────────────────
    found_skills = []
    found_tools = []
    for skill in KNOWN_SKILLS:
        # Use word boundary matching for short terms
        if len(skill) <= 3:
            pattern = r"\b" + re.escape(skill) + r"\b"
            if re.search(pattern, text_lower):
                # Classify as tool if it's a technology/framework
                if skill in {"git", "sql", "aws", "gcp", "css", "r"}:
                    found_tools.append(skill)
                else:
                    found_skills.append(skill)
        else:
            if skill in text_lower:
                # Frameworks/platforms → tools; languages/concepts → skills
                tools_keywords = {
                    "docker", "kubernetes", "terraform", "jenkins",
                    "github actions", "gitlab", "jira", "redis",
                    "elasticsearch", "dynamodb", "sqlite",
                    "tailwind", "bootstrap",
                }
                if skill in tools_keywords:
                    found_tools.append(skill)
                else:
                    found_skills.append(skill)

    # ── Extract experience ──────────────────────────────────────
    exp_match = EXPERIENCE_PATTERN.search(resume_text)
    experience = f"{exp_match.group(1)} years" if exp_match else "not specified"

    # ── Extract role ────────────────────────────────────────────
    detected_role = "not specified"
    for role in KNOWN_ROLES:
        if role in text_lower:
            detected_role = role.title()
            break

    return {
        "candidate_skills": list(set(found_skills)),
        "candidate_tools": list(set(found_tools)),
        "candidate_experience": experience,
        "candidate_role": detected_role,
    }


def generate_resume_questions(parsed_resume: dict) -> list:
    """
    Generate personalized interview questions from parsed resume data.

    Args:
        parsed_resume: output from parse_resume()

    Returns:
        List of resume-conditioned question strings.
    """
    questions = []
    skills = parsed_resume.get("candidate_skills", [])
    tools = parsed_resume.get("candidate_tools", [])
    role = parsed_resume.get("candidate_role", "not specified")
    experience = parsed_resume.get("candidate_experience", "not specified")

    # ── Skill-based questions ───────────────────────────────────
    for skill in skills[:5]:  # cap at 5 to avoid overload
        questions.append(
            f"You mentioned {skill.title()} in your background. "
            f"Can you describe a project where you used {skill.title()} "
            f"to solve a challenging problem?"
        )

    # ── Tool-based questions ────────────────────────────────────
    for tool in tools[:3]:
        questions.append(
            f"Tell me about your experience with {tool.title()}. "
            f"How have you used it in a production environment?"
        )

    # ── Role-based question ─────────────────────────────────────
    if role != "not specified":
        questions.append(
            f"As a {role}, what do you consider the most critical "
            f"skill for success in this kind of role?"
        )

    # ── Experience-based question ───────────────────────────────
    if experience != "not specified":
        questions.append(
            f"With {experience} of experience, what is the most "
            f"important lesson you have learned in your career?"
        )

    return questions
