from app.models import BaseAttributes, IdentityProfile, NpcIdentity, Personality, SkillProficiency


IDENTITY_SKILL_DOMAINS = {
    "merchant": ("trade", "appraisal", "negotiation"),
    "warrior": ("combat", "weapon_use", "guarding"),
    "producer": ("crafting", "farming", "forging", "gathering", "repair"),
    "official": ("administration", "leadership", "law"),
    "physician": ("medicine", "diagnosis", "care"),
    "monster": ("combat", "predation", "survival"),
    "civilian": ("labor", "social", "survival"),
    "player_related": ("social", "support", "survival"),
}


def build_identity_profile(role: str, base: BaseAttributes, personality: Personality) -> IdentityProfile:
    role = normalize_role(role)
    identity_scores = score_identities(base)
    identity = identity_for_role(role) or max(identity_scores, key=identity_scores.get)
    interests = profession_interests(role, personality)
    profession = profession_for(role, identity.value, interests)
    skills = build_skills(identity.value, profession, base, personality, interests)
    return IdentityProfile(
        identity=identity,
        profession=profession,
        identity_scores=identity_scores,
        profession_interests=interests,
        skills=skills,
        capability_notes=capability_notes(base, skills),
    )


def score_identities(base: BaseAttributes) -> dict[str, int]:
    return {
        "merchant": clamp_score(base.logic * 12 + base.influence * 12 + base.perception * 7 + base.technique * 4),
        "warrior": clamp_score(base.strength * 13 + base.endurance * 10 + base.technique * 9 + base.perception * 5),
        "producer": clamp_score(base.technique * 13 + base.endurance * 8 + base.logic * 6 + base.perception * 5),
        "official": clamp_score(base.logic * 12 + base.influence * 12 + base.perception * 6 + base.endurance * 4),
        "physician": clamp_score(base.logic * 11 + base.perception * 11 + base.technique * 8 + base.influence * 4),
    }


def identity_for_role(role: str) -> NpcIdentity | None:
    role = normalize_role(role)
    mapping = {
        "merchant": NpcIdentity.merchant,
        "guard": NpcIdentity.warrior,
        "hunter": NpcIdentity.warrior,
        "warrior": NpcIdentity.warrior,
        "producer": NpcIdentity.producer,
        "farmer": NpcIdentity.producer,
        "blacksmith": NpcIdentity.producer,
        "official": NpcIdentity.official,
        "village_chief": NpcIdentity.official,
        "physician": NpcIdentity.physician,
        "monster": NpcIdentity.monster,
        "player_related": NpcIdentity.player_related,
    }
    return mapping.get(role)


def profession_interests(role: str, personality: Personality) -> dict[str, int]:
    role = normalize_role(role)
    interests = {
        "guarding": clamp_score(personality.loyalty * 5 + personality.discipline * 4 + personality.bravery * 3),
        "hunting": clamp_score(personality.bravery * 4 + personality.curiosity * 4 + personality.aggression * 4),
        "trading": clamp_score(personality.greed * 4 + personality.ambition * 4 + personality.prudence * 3),
        "farming": clamp_score(personality.patience * 4 + personality.discipline * 3 + personality.kindness * 3),
        "forging": clamp_score(personality.discipline * 4 + personality.patience * 4 + personality.ambition * 3),
        "crafting": clamp_score(personality.patience * 4 + personality.discipline * 4 + personality.curiosity * 3),
        "governing": clamp_score(personality.conformity * 4 + personality.discipline * 4 + personality.ambition * 4),
        "healing": clamp_score(personality.empathy * 5 + personality.kindness * 4 + personality.prudence * 3),
        "raiding": clamp_score(personality.aggression * 5 + personality.bravery * 4 + personality.greed * 3),
    }
    role_boosts = {
        "guard": "guarding",
        "hunter": "hunting",
        "merchant": "trading",
        "producer": "crafting",
        "farmer": "farming",
        "blacksmith": "forging",
        "official": "governing",
        "village_chief": "governing",
        "physician": "healing",
        "monster": "raiding",
    }
    boosted = role_boosts.get(role)
    if boosted is not None:
        interests[boosted] = clamp_score(interests[boosted] + 20)
    return interests


def profession_for(role: str, identity: str, interests: dict[str, int]) -> str:
    role = normalize_role(role)
    if role in {"guard", "hunter", "merchant", "farmer", "blacksmith", "physician", "village_chief", "monster"}:
        return role
    if role in {"producer", "official", "physician", "warrior"}:
        top_interest = max(interests, key=interests.get)
        return f"{role}:{top_interest}"
    if identity == "warrior":
        return "guard" if interests["guarding"] >= interests["hunting"] else "hunter"
    if identity == "merchant":
        return "merchant"
    if identity == "producer":
        return "producer:crafting"
    if identity == "official":
        return "official:governing"
    if identity == "physician":
        return "physician:healing"
    return "villager"


def build_skills(
    identity: str,
    profession: str,
    base: BaseAttributes,
    personality: Personality,
    interests: dict[str, int],
) -> list[SkillProficiency]:
    domains = set(IDENTITY_SKILL_DOMAINS.get(identity, IDENTITY_SKILL_DOMAINS["civilian"]))
    domains.update(profession_domains(profession))
    return [
        SkillProficiency(
            skill_id=domain,
            domain=domain,
            level=skill_level(domain, base, personality, interests),
            affinity=skill_affinity(domain, personality, interests),
        )
        for domain in sorted(domains)
    ]


def profession_domains(profession: str) -> tuple[str, ...]:
    if profession == "guard":
        return ("combat", "guarding", "weapon_use")
    if profession == "hunter":
        return ("combat", "hunting", "tracking")
    if profession == "merchant":
        return ("trade", "appraisal", "negotiation")
    if profession == "farmer":
        return ("farming", "gathering", "labor", "survival")
    if profession == "blacksmith":
        return ("forging", "crafting", "repair", "weapon_use")
    if profession == "physician":
        return ("medicine", "diagnosis", "care")
    if profession == "village_chief":
        return ("administration", "leadership", "law", "negotiation")
    if "crafting" in profession:
        return ("crafting", "repair", "gathering")
    if "governing" in profession:
        return ("administration", "leadership", "law")
    if "healing" in profession:
        return ("medicine", "diagnosis", "care")
    if profession == "monster":
        return ("combat", "predation", "survival")
    return ()


def skill_level(domain: str, base: BaseAttributes, personality: Personality, interests: dict[str, int]) -> int:
    formulas = {
        "combat": base.strength * 8 + base.endurance * 6 + base.technique * 6 + personality.bravery * 3,
        "weapon_use": base.strength * 6 + base.technique * 9 + base.endurance * 4,
        "guarding": base.perception * 7 + base.endurance * 5 + personality.loyalty * 5 + personality.discipline * 4,
        "hunting": base.perception * 8 + base.technique * 6 + base.endurance * 5 + personality.curiosity * 3,
        "tracking": base.perception * 10 + base.endurance * 4 + personality.curiosity * 4,
        "trade": base.logic * 7 + base.influence * 9 + base.perception * 4 + personality.prudence * 3,
        "appraisal": base.logic * 8 + base.perception * 8 + base.technique * 3,
        "negotiation": base.influence * 10 + base.logic * 4 + personality.empathy * 3,
        "crafting": base.technique * 10 + base.logic * 5 + base.endurance * 4 + personality.discipline * 3,
        "farming": base.endurance * 7 + base.technique * 6 + base.perception * 5 + personality.patience * 4,
        "forging": base.strength * 6 + base.technique * 9 + base.endurance * 5 + personality.discipline * 4,
        "repair": base.technique * 9 + base.logic * 6 + personality.prudence * 3,
        "gathering": base.perception * 7 + base.endurance * 6 + base.technique * 4,
        "administration": base.logic * 9 + base.influence * 7 + personality.discipline * 4,
        "leadership": base.influence * 9 + base.logic * 5 + personality.loyalty * 4,
        "law": base.logic * 10 + base.influence * 4 + personality.conformity * 4,
        "medicine": base.logic * 8 + base.perception * 8 + base.technique * 4 + personality.empathy * 3,
        "diagnosis": base.perception * 10 + base.logic * 7 + personality.prudence * 3,
        "care": base.influence * 5 + base.perception * 5 + personality.kindness * 5 + personality.empathy * 5,
        "predation": base.strength * 7 + base.perception * 7 + personality.aggression * 5,
        "survival": base.endurance * 8 + base.perception * 6 + personality.prudence * 4,
        "labor": base.endurance * 8 + base.strength * 5 + base.technique * 4,
        "social": base.influence * 8 + personality.empathy * 4 + personality.conformity * 3,
        "support": base.influence * 6 + base.perception * 4 + personality.kindness * 5,
    }
    interest_bonus = int(max(interests.values(), default=0) * 0.08)
    return clamp_score(int(formulas.get(domain, 35) * 0.85) + interest_bonus)


def skill_affinity(domain: str, personality: Personality, interests: dict[str, int]) -> int:
    relevant_interest = max(interests.values(), default=50)
    temperament = personality.curiosity + personality.discipline + personality.ambition - personality.conformity
    if domain in {"combat", "weapon_use", "predation"}:
        temperament += personality.bravery + personality.aggression - personality.prudence
    if domain in {"medicine", "care", "negotiation"}:
        temperament += personality.empathy + personality.kindness - personality.greed
    return max(-100, min(100, int(relevant_interest * 0.5 + temperament * 2 - 50)))


def capability_notes(base: BaseAttributes, skills: list[SkillProficiency]) -> list[str]:
    notes: list[str] = []
    skill_by_id = {skill.skill_id: skill.level for skill in skills}
    if base.strength < 4:
        notes.append("weak_weapon_handling")
    if skill_by_id.get("combat", 0) < 35:
        notes.append("combat_work_high_risk")
    if skill_by_id.get("crafting", 0) < 35:
        notes.append("craft_output_unreliable")
    if skill_by_id.get("medicine", 0) < 35:
        notes.append("medical_work_unreliable")
    return notes


def skill_lookup(skills: list[SkillProficiency], skill_id: str) -> int:
    for skill in skills:
        if skill.skill_id == skill_id:
            return skill.level
    return 0


def clamp_score(value: int) -> int:
    return max(0, min(value, 100))


def normalize_role(role: str) -> str:
    return role.split(".", 1)[1] if "." in role else role
