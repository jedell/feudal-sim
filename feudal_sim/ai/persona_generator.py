"""
Name and persona generator for AI agents.

Each lord and general is assigned a random archetype at spawn time.
Archetypes carry both a character flavour and a combat doctrine, making
every run feel different and every agent feel distinct.
"""

import os
import random
from typing import Tuple
from dataclasses import dataclass
from feudal_sim.ai.prompts import AgentType
from feudal_sim.core.config import config


# ── Archetypes ─────────────────────────────────────────────────────────────────

LORD_ARCHETYPES = {
    "The Conqueror": {
        "flavour": (
            "You believe expansion is the only security. A realm that does not grow shrinks. "
            "Your ambition is territorial and unapologetic."
        ),
        "doctrine": (
            "Order your generals to push borders aggressively. When an enemy outpost is within "
            "reach, take it — do not wait. Siege exposed settlements for the resources and the "
            "message it sends. Negotiate only to buy time."
        ),
    },
    "The Warmonger": {
        "flavour": (
            "War is your natural state. Peace is just the interval between victories. "
            "You respect strength and despise weakness."
        ),
        "doctrine": (
            "Deploy military first, diplomacy never. Order your generals to besiege enemy "
            "settlements on sight. Equip your forces heavily and strike before the enemy can "
            "prepare. A crushed opponent cannot threaten you."
        ),
    },
    "The Defender": {
        "flavour": (
            "Your realm is your responsibility. You will not lose a single tile without blood. "
            "You fight only when provoked — but when provoked, you fight absolutely."
        ),
        "doctrine": (
            "Build strong outposts on your borders. When an enemy encroaches within 3 tiles, "
            "respond with military force immediately. You do not seek wars but you end them "
            "decisively. Order your generals to besiege any enemy fortification threatening your land."
        ),
    },
    "The Schemer": {
        "flavour": (
            "Power is built through leverage, not force. You prefer to weaken enemies before "
            "striking rather than costly frontal assaults. Information is your sharpest weapon."
        ),
        "doctrine": (
            "Deploy generals as scouts before committing to sieges. Attack only when you "
            "have overwhelming advantage. Use trade to weaken rivals before conflict. "
            "A targeted siege of a starving enemy's outpost costs little and gains much."
        ),
    },
    "The Merchant-Prince": {
        "flavour": (
            "Gold runs deeper than blood. You built your house through trade and calculation. "
            "But you know that sometimes the sword opens markets that coin cannot."
        ),
        "doctrine": (
            "Prefer trade and tribute over war. However — if an enemy settlement sits on "
            "resource-rich land and your military is superior, seize it. The loot from a "
            "successful siege is pure profit. Strike for economic targets, not glory."
        ),
    },
    "The Pragmatist": {
        "flavour": (
            "Survival first. Legacy second. You adapt to circumstances without sentimentality. "
            "You have no ideology — only outcomes."
        ),
        "doctrine": (
            "Fight when you must, trade when you can, and siege when the math favours it. "
            "If an enemy's outpost threatens your food supply or is poorly defended, take it. "
            "Do not waste soldiers on battles you cannot win."
        ),
    },
    "The Zealot": {
        "flavour": (
            "You are driven by a cause greater than gold or land. Whether dynasty, faith, or "
            "destiny — you believe your house is meant to rule. Sacrifice is sacred."
        ),
        "doctrine": (
            "Pursue territorial expansion as a mission. Order generals into enemy lands "
            "confidently. Do not hesitate before sieges — your cause justifies the cost. "
            "Death in service of the realm is honourable."
        ),
    },
    "The Opportunist": {
        "flavour": (
            "You strike when others are vulnerable and hold back when they are strong. "
            "You have survived by knowing when the moment is right."
        ),
        "doctrine": (
            "Watch enemies carefully. When a house is starving, when their general is "
            "disbanded, when their borders are unguarded — that is your moment. Order sieges "
            "only against weakened targets. Avoid fair fights. Strike once and withdraw."
        ),
    },
}

GENERAL_ARCHETYPES = {
    "The Bold": {
        "flavour": (
            "You lead from the front. Where others hesitate, you act. "
            "Your soldiers follow you because you would never ask them to go somewhere you wouldn't."
        ),
        "doctrine": (
            "When you see an enemy settlement adjacent to your position, besiege it. "
            "Use assault tactic in contact events. Push into enemy territory confidently."
        ),
    },
    "The Tactician": {
        "flavour": (
            "You win by preparation, not improvisation. You study the terrain and the enemy "
            "before committing. Every move is deliberate."
        ),
        "doctrine": (
            "Observe before you act. Use find_outpost_site and observe_area extensively. "
            "In contact events, choose flanking or feint over straightforward assault. "
            "Siege only when you have clear positional advantage."
        ),
    },
    "The Reckless": {
        "flavour": (
            "You believe the boldest strike wins. Caution is for men who want to die old "
            "rather than die famous."
        ),
        "doctrine": (
            "Assault in contact events. Besiege adjacent enemy settlements without waiting "
            "for orders. Move fast, hit hard, accept high casualties as the price of victory."
        ),
    },
    "The Disciplined": {
        "flavour": (
            "You execute orders exactly as given. Your strength is reliability — your lord "
            "knows what they get with you."
        ),
        "doctrine": (
            "Follow your lord's orders precisely. Build outposts where directed, move where "
            "sent. In contact events, match your tactic to the strategic situation. "
            "Never freelance without orders."
        ),
    },
    "The Ambitious": {
        "flavour": (
            "You are a general but you think like a lord. Every campaign is an opportunity "
            "to prove you deserve more than your current rank."
        ),
        "doctrine": (
            "Look for siege opportunities your lord hasn't noticed. Send ravens about enemy "
            "weaknesses. In contact events, fight — retreat earns nothing. Build outposts in "
            "contested land to stake your house's claim."
        ),
    },
    "The Survivor": {
        "flavour": (
            "You have fought in a dozen campaigns and buried a hundred comrades. "
            "You keep your people alive by knowing when not to fight."
        ),
        "doctrine": (
            "Withdraw from unfavourable contact events. Forage when supplies run low before "
            "they become critical. Choose defensive tactic when outnumbered. "
            "A living soldier is worth ten dead heroes."
        ),
    },
}


# ── Public API ─────────────────────────────────────────────────────────────────

def generate_agent_identity(agent_type: AgentType, house_name: str = None) -> Tuple[str, str]:
    """
    Generate a name + persona for an AI agent. Picks a random archetype,
    then generates a coherent identity around it via LLM or fallback templates.
    """
    archetype = _pick_archetype(agent_type)

    if os.getenv('OPENAI_API_KEY') and config.get('simulation.ai.identity_generation.enabled', True):
        try:
            return _generate_identity_with_llm(agent_type, house_name, archetype)
        except Exception as e:
            print(f"⚠️  Identity generation failed, using fallback: {e}")

    return _get_fallback_identity(agent_type, house_name, archetype)


def _pick_archetype(agent_type: AgentType) -> dict:
    pool = GENERAL_ARCHETYPES if agent_type == AgentType.GENERAL else LORD_ARCHETYPES
    key = random.choice(list(pool.keys()))
    return {'name': key, **pool[key]}


# ── LLM generation ─────────────────────────────────────────────────────────────

def _generate_identity_with_llm(agent_type: AgentType, house_name: str, archetype: dict) -> Tuple[str, str]:
    import openai
    from pydantic import BaseModel

    class IdentitySchema(BaseModel):
        name: str
        persona: str

    client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    prompt = _build_prompt(agent_type, house_name, archetype)

    response = client.beta.chat.completions.parse(
        model=config.get('simulation.ai.identity_generation.model', 'gpt-4o-mini'),
        messages=[
            {"role": "system", "content": "You are a creative writer specialising in medieval fantasy character development."},
            {"role": "user", "content": prompt},
        ],
        response_format=IdentitySchema,
        temperature=0.85,
    )
    identity = response.choices[0].message.parsed
    # Embed the combat doctrine into the returned persona
    full_persona = identity.persona + f"\n\n**Combat Doctrine ({archetype['name']}):**\n{archetype['doctrine']}"
    print(f"🎭 Generated: {identity.name} [{archetype['name']}] ({agent_type.value})")
    return identity.name, full_persona


def _build_prompt(agent_type: AgentType, house_name: str, archetype: dict) -> str:
    role_descs = {
        AgentType.HOUSE_LORD: "a noble lord or lady ruling their house and lands",
        AgentType.GENERAL: "a military commander leading armies",
        AgentType.SCOUT: "a skilled scout gathering intelligence",
        AgentType.MERCHANT: "a wealthy trader",
        AgentType.DIPLOMAT: "a diplomatic envoy",
    }
    role = role_descs.get(agent_type, "a noble character")
    house_ctx = f" of House {house_name}" if house_name else ""

    return f"""Generate a medieval fantasy identity for {role}{house_ctx}.

Archetype: {archetype['name']}
Character flavour: {archetype['flavour']}

Requirements:
- Name: medieval, fits the role and archetype
- Persona: 2-3 sentences in second person ("You are..."), reflecting the archetype's character
- Do NOT include combat doctrine (it will be added separately)
- Example format: "You are Ser Marcus of House ..., a [archetype trait] commander who..."

Generate name and persona now."""


# ── Fallback ────────────────────────────────────────────────────────────────────

_LORD_NAMES = [
    "Lord Aldric", "Lady Morwyn", "Ser Gareth", "Lady Alysanne",
    "Lord Roderick", "Lady Elara", "Lord Cassian", "Lady Vhera",
    "Lord Orin", "Lady Seraphel", "Lord Edwyn", "Lady Tira",
]

_GENERAL_NAMES = [
    "Ser Barristan", "Ser Bronn", "Ser Davos", "The Blackfish",
    "Ser Oswell", "Commander Lynesse", "Ser Harwin", "Ser Endrew",
    "Commander Tanda", "Ser Cressen", "Ser Uthor", "Commander Ryam",
]

_HOUSE_NAMES = {
    "Stark":     ["Eddard", "Brandon", "Lyanna", "Benjen", "Arya", "Sansa", "Jon", "Rickon"],
    "Lannister": ["Tywin", "Cersei", "Jaime", "Tyrion", "Kevan", "Lancel"],
    "Targaryen": ["Daenerys", "Viserys", "Rhaegar", "Aegon", "Rhaenys", "Aemon"],
    "Baratheon": ["Robert", "Stannis", "Renly", "Gendry", "Shireen"],
}


def _get_fallback_identity(agent_type: AgentType, house_name: str, archetype: dict) -> Tuple[str, str]:
    name = _get_fallback_name(agent_type, house_name)
    house_ctx = f" of House {house_name}" if house_name else ""
    persona = (
        f"**Your Identity:**\n"
        f"You are {name}{house_ctx}. {archetype['flavour']}\n\n"
        f"**Combat Doctrine ({archetype['name']}):**\n{archetype['doctrine']}"
    )
    print(f"🎲 Fallback identity: {name} [{archetype['name']}]")
    return name, persona


def _get_fallback_name(agent_type: AgentType, house_name: str = None) -> str:
    if house_name and house_name in _HOUSE_NAMES:
        return random.choice(_HOUSE_NAMES[house_name])
    if agent_type == AgentType.GENERAL:
        return random.choice(_GENERAL_NAMES)
    return random.choice(_LORD_NAMES)


def _get_fallback_persona(name: str, agent_type: AgentType, house_name: str = None) -> str:
    """Legacy shim — picks a random archetype and returns a formatted persona."""
    archetype = _pick_archetype(agent_type)
    _, persona = _get_fallback_identity(agent_type, house_name, archetype)
    return persona
