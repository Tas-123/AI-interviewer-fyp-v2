/** Role title / skill catalogs for lobby when invite meta is missing. */

export const ROLE_META = {
    junior_ai_engineer: {
        display_title: "Junior AI Engineer",
        description:
            "A real-time voice interview for Junior AI Engineer candidates, with adaptive technical questions and an automated evaluation report.",
        suggested_skills: [
            "Python",
            "Machine Learning",
            "Deep Learning",
            "NLP",
            "Computer Vision",
            "FastAPI",
            "PyTorch",
            "TensorFlow",
            "Data Preprocessing",
            "Model Evaluation",
        ],
    },
    junior_frontend_developer: {
        display_title: "Junior Frontend Developer",
        description:
            "A real-time voice interview for Junior Frontend Developer candidates, covering UI, JavaScript, frameworks, and API integration.",
        suggested_skills: [
            "HTML",
            "CSS",
            "JavaScript",
            "TypeScript",
            "React",
            "Next.js",
            "Vue",
            "Tailwind",
            "REST APIs",
            "Responsive Design",
        ],
    },
    junior_backend_developer: {
        display_title: "Junior Backend Developer",
        description:
            "A real-time voice interview for Junior Backend Developer candidates, covering APIs, databases, auth, and deployment basics.",
        suggested_skills: [
            "Python",
            "Node.js",
            "FastAPI",
            "Express",
            "SQL",
            "PostgreSQL",
            "REST APIs",
            "Docker",
            "Authentication",
            "MongoDB",
        ],
    },
};

export function metaForRole(targetRole) {
    const key = (targetRole || "junior_ai_engineer").trim().toLowerCase();
    return ROLE_META[key] || ROLE_META.junior_ai_engineer;
}

export function applyInterviewMeta(refs, meta = {}) {
    const title = (meta.display_title || "Interview").trim();
    const description =
        (meta.description || "").trim() ||
        `A real-time voice interview for ${title} candidates. Enter your name, select your skills, then start when you are ready.`;
    const skills = Array.isArray(meta.suggested_skills) ? meta.suggested_skills : [];

    if (refs.preInterviewTitle) {
        refs.preInterviewTitle.textContent = `${title} Interview`;
    }
    if (refs.preInterviewDescription) {
        refs.preInterviewDescription.textContent = description;
    }
    document.title = `${title} — AI Voice Interview`;

    renderSkillChips(refs, skills);
}

export function renderSkillChips(refs, skills) {
    const host = refs.preSkillChips;
    if (!host) return;
    host.innerHTML = "";
    const list = skills.length
        ? skills
        : metaForRole("junior_ai_engineer").suggested_skills;
    list.forEach((skill) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "skill-chip";
        btn.textContent = skill;
        btn.dataset.skill = skill;
        btn.setAttribute("aria-pressed", "false");
        btn.addEventListener("click", () => {
            const on = btn.getAttribute("aria-pressed") === "true";
            btn.setAttribute("aria-pressed", on ? "false" : "true");
            btn.classList.toggle("is-selected", !on);
            syncSelectedSkillsToShell(refs);
        });
        host.appendChild(btn);
    });
}

export function getSelectedSkills(refs) {
    if (!refs.preSkillChips) return [];
    return Array.from(refs.preSkillChips.querySelectorAll(".skill-chip.is-selected")).map(
        (el) => el.dataset.skill || el.textContent.trim()
    );
}

export function syncSelectedSkillsToShell(refs) {
    const skills = getSelectedSkills(refs);
    const notes = refs.preInputResume?.value?.trim() || "";
    const parts = [];
    if (skills.length) parts.push(skills.join(", "));
    if (notes) parts.push(notes);
    const combined = parts.join(". ");
    if (refs.inputResume) refs.inputResume.value = combined;
    refs._selectedSkills = skills;
}
