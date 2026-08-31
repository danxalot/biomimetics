"""
Enhanced Skills Manager - MCP Skills Framework with Markdown Integration

Augments the existing SkillsManager to:
1. Convert markdown skill documents (/mcp_skills/) to callable tool definitions
2. Track effectiveness metrics per skill
3. Expose skills via MCP with full metadata
4. Enable skill discovery and recommendation

Separate from ReasoningBank - this tracks skill effectiveness/usage,
while ReasoningBank tracks reasoning trajectories and learning.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
import re

logger = logging.getLogger(__name__)


class SkillSource(Enum):
    """Source of skill definition"""
    CORE = "core"              # Built-in Anthropic skills
    MARKDOWN = "markdown"      # From /mcp_skills/ documentation
    LEARNED = "learned"        # Generated from agent learning


@dataclass
class SkillMetadata:
    """Extended skill metadata from markdown"""
    skill_id: str              # Unique identifier
    name: str                  # Display name
    description: str           # What the skill does
    category: str              # reasoning, technical, creative, meta, communication
    level: str                 # novice, intermediate, advanced, expert, master
    source: SkillSource        # Where skill came from
    
    # Effectiveness tracking
    usage_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    last_used: Optional[str] = None
    effectiveness_score: float = 1.0  # 0.0-1.0
    
    # Documentation
    parameters: Dict[str, Any] = None     # Input parameters
    returns: str = ""                      # What it returns
    prerequisites: List[str] = None        # Skills needed first
    related_skills: List[str] = None       # Complementary skills
    
    # Learning
    weaknesses: List[str] = None           # Identified gaps
    improvements: List[str] = None         # Suggested enhancements
    use_cases: List[str] = None            # When to use
    anti_patterns: List[str] = None        # When NOT to use
    
    # Markdown source
    markdown_file: Optional[str] = None
    markdown_path: Optional[str] = None
    
    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}
        if self.prerequisites is None:
            self.prerequisites = []
        if self.related_skills is None:
            self.related_skills = []
        if self.weaknesses is None:
            self.weaknesses = []
        if self.improvements is None:
            self.improvements = []
        if self.use_cases is None:
            self.use_cases = []
        if self.anti_patterns is None:
            self.anti_patterns = []
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate"""
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 1.0
    
    @property
    def needs_improvement(self) -> bool:
        """Whether skill needs improvement based on metrics"""
        # Needs improvement if success rate < 70% or has 3+ weaknesses
        return self.success_rate < 0.7 or len(self.weaknesses) >= 3
    
    @property
    def recommended(self) -> bool:
        """Whether skill is recommended based on effectiveness"""
        return self.effectiveness_score >= 0.7 and self.usage_count > 0
    
    def to_mcp_tool(self) -> Dict[str, Any]:
        """Convert to MCP tool definition"""
        return {
            'name': self.skill_id,
            'description': f"{self.description} (Effectiveness: {self.effectiveness_score:.0%}, Used: {self.usage_count}x)",
            'inputSchema': {
                'type': 'object',
                'properties': self.parameters,
                'required': [p for p, prop in self.parameters.items() if not prop.get('optional', False)]
            },
            'metadata': {
                'category': self.category,
                'level': self.level,
                'source': self.source.value,
                'effectiveness': self.effectiveness_score,
                'usage_count': self.usage_count,
                'success_rate': self.success_rate,
                'related_skills': self.related_skills,
                'prerequisites': self.prerequisites
            }
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['source'] = self.source.value
        data['last_used'] = self.last_used
        return data


class MarkdownSkillParser:
    """Parse markdown skill files to extract metadata"""
    
    @staticmethod
    def parse_skill_file(file_path: Path) -> Optional[SkillMetadata]:
        """
        Parse a markdown skill file and extract metadata.
        
        Expected markdown structure:
        # Skill Name
        Description paragraph
        
        ## Parameters
        - param1: description
        
        ## Returns
        Description of return value
        
        ## Prerequisites
        - skill1
        - skill2
        
        ## Use Cases
        - Case 1
        - Case 2
        """
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            
            # Extract title (first H1)
            title_match = re.search(r'^# (.+)$', content, re.MULTILINE)
            if not title_match:
                logger.warning(f"No title found in {file_path.name}")
                return None
            
            title = title_match.group(1).strip()
            skill_id = file_path.stem.lower().replace(' ', '_')
            
            # Extract description (first paragraph after title)
            desc_match = re.search(
                r'^# .+?\n\n(.+?)(?:\n##|\Z)',
                content,
                re.MULTILINE | re.DOTALL
            )
            description = desc_match.group(1).strip() if desc_match else ""
            
            # Extract sections
            parameters = MarkdownSkillParser._extract_parameters(content)
            returns = MarkdownSkillParser._extract_section(content, "Returns")
            prerequisites = MarkdownSkillParser._extract_list(content, "Prerequisites")
            related_skills = MarkdownSkillParser._extract_list(content, "Related Skills")
            use_cases = MarkdownSkillParser._extract_list(content, "Use Cases")
            anti_patterns = MarkdownSkillParser._extract_list(content, "Anti-Patterns")
            
            # Infer category from content
            category = MarkdownSkillParser._infer_category(content)
            
            # Infer level from content
            level = MarkdownSkillParser._infer_level(content)
            
            return SkillMetadata(
                skill_id=skill_id,
                name=title,
                description=description[:200],  # Truncate to 200 chars
                category=category,
                level=level,
                source=SkillSource.MARKDOWN,
                parameters=parameters,
                returns=returns[:100],
                prerequisites=prerequisites,
                related_skills=related_skills,
                use_cases=use_cases,
                anti_patterns=anti_patterns,
                markdown_file=file_path.name,
                markdown_path=str(file_path)
            )
        
        except Exception as e:
            logger.error(f"Error parsing skill file {file_path}: {e}")
            return None
    
    @staticmethod
    def _extract_section(content: str, section_name: str) -> str:
        """Extract text from a markdown section"""
        pattern = rf'## {section_name}\s*\n(.+?)(?:\n##|\Z)'
        match = re.search(pattern, content, re.DOTALL)
        return match.group(1).strip() if match else ""
    
    @staticmethod
    def _extract_list(content: str, section_name: str) -> List[str]:
        """Extract list items from a markdown section"""
        section = MarkdownSkillParser._extract_section(content, section_name)
        items = re.findall(r'^[-*]\s+(.+)$', section, re.MULTILINE)
        return [item.strip() for item in items]
    
    @staticmethod
    def _extract_parameters(content: str) -> Dict[str, Any]:
        """Extract parameter definitions from markdown"""
        section = MarkdownSkillParser._extract_section(content, "Parameters")
        parameters = {}
        
        # Parse parameter list: "- name (type, optional): description"
        pattern = r'^-\s+(\w+)(?:\s*\(([^)]+)\))?:\s*(.+)$'
        for match in re.finditer(pattern, section, re.MULTILINE):
            name, type_str, desc = match.groups()
            param_type = type_str.split(',')[0].strip() if type_str else "string"
            optional = "optional" in (type_str or "").lower()
            
            parameters[name] = {
                'type': param_type,
                'description': desc.strip(),
                'optional': optional
            }
        
        return parameters
    
    @staticmethod
    def _infer_category(content: str) -> str:
        """Infer skill category from content"""
        content_lower = content.lower()
        
        if any(word in content_lower for word in ['memory', 'reason', 'logic', 'analysis']):
            return 'reasoning'
        elif any(word in content_lower for word in ['code', 'docker', 'api', 'database', 'system']):
            return 'technical'
        elif any(word in content_lower for word in ['creative', 'novel', 'innovative', 'alternative']):
            return 'creative'
        elif any(word in content_lower for word in ['learn', 'improve', 'assess', 'adapt', 'reflect']):
            return 'meta'
        elif any(word in content_lower for word in ['communication', 'explain', 'clarify', 'documentation']):
            return 'communication'
        
        return 'technical'  # default
    
    @staticmethod
    def _infer_level(content: str) -> str:
        """Infer skill level from content"""
        content_lower = content.lower()
        
        if any(word in content_lower for word in ['master', 'expert level', 'sophisticated']):
            return 'master'
        elif any(word in content_lower for word in ['expert', 'advanced', 'complex']):
            return 'expert'
        elif any(word in content_lower for word in ['advanced', 'intermediate']):
            return 'advanced'
        elif any(word in content_lower for word in ['beginner', 'basic', 'simple']):
            return 'intermediate'
        
        return 'intermediate'  # default


class EnhancedSkillsManager:
    """
    Enhanced Skills Manager with markdown integration and effectiveness tracking
    
    Features:
    - Loads core Anthropic skills
    - Scans and parses markdown skill files
    - Tracks skill effectiveness and usage
    - Exposes skills as MCP tools
    - Provides skill recommendations
    """
    
    def __init__(self, data_dir: Path, skills_dir: Optional[Path] = None):
        """
        Initialize enhanced skills manager
        
        Args:
            data_dir: Directory for skill registry and learning logs
            skills_dir: Directory containing markdown skill files (default: /app/skills)
        """
        self.data_dir = Path(data_dir)
        self.skills_dir = Path(skills_dir) if skills_dir else Path('/app/skills')
        
        self.skills_registry_file = self.data_dir / "skills_registry_enhanced.json"
        self.learning_log_file = self.data_dir / "skill_learning_events.json"
        
        # Initialize directories
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Skill registry: skill_id -> SkillMetadata
        self.skills: Dict[str, SkillMetadata] = {}
        
        # Load existing registry
        self._load_registry()
        
        # Load markdown skills
        self._load_markdown_skills()
    
    def _load_registry(self):
        """Load existing skill registry from disk"""
        if self.skills_registry_file.exists():
            try:
                with open(self.skills_registry_file, 'r') as f:
                    data = json.load(f)
                    for skill_id, skill_data in data.items():
                        # Reconstruct SkillMetadata
                        source = SkillSource(skill_data.get('source', 'core'))
                        metadata = SkillMetadata(
                            skill_id=skill_id,
                            name=skill_data.get('name', ''),
                            description=skill_data.get('description', ''),
                            category=skill_data.get('category', 'technical'),
                            level=skill_data.get('level', 'intermediate'),
                            source=source,
                            usage_count=skill_data.get('usage_count', 0),
                            success_count=skill_data.get('success_count', 0),
                            failure_count=skill_data.get('failure_count', 0),
                            last_used=skill_data.get('last_used'),
                            effectiveness_score=skill_data.get('effectiveness_score', 1.0),
                            parameters=skill_data.get('parameters', {}),
                            returns=skill_data.get('returns', ''),
                            prerequisites=skill_data.get('prerequisites', []),
                            related_skills=skill_data.get('related_skills', []),
                            weaknesses=skill_data.get('weaknesses', []),
                            improvements=skill_data.get('improvements', []),
                            use_cases=skill_data.get('use_cases', []),
                            anti_patterns=skill_data.get('anti_patterns', []),
                            markdown_file=skill_data.get('markdown_file'),
                            markdown_path=skill_data.get('markdown_path')
                        )
                        self.skills[skill_id] = metadata
                
                logger.info(f"✅ Loaded {len(self.skills)} skills from registry")
            except Exception as e:
                logger.error(f"Error loading skill registry: {e}")
        
        # Initialize with core skills if empty
        if len(self.skills) == 0:
            self._initialize_core_skills()
    
    def _initialize_core_skills(self):
        """Initialize with core Anthropic skills"""
        core_skills = [
            # Reasoning
            SkillMetadata(
                skill_id='logical_analysis',
                name='Logical Analysis',
                description='Break down problems using logical frameworks and systematic reasoning',
                category='reasoning',
                level='advanced',
                source=SkillSource.CORE,
                use_cases=['Complex problem solving', 'Debugging issues', 'Decision making']
            ),
            SkillMetadata(
                skill_id='critical_thinking',
                name='Critical Thinking',
                description='Evaluate information critically and identify assumptions',
                category='reasoning',
                level='advanced',
                source=SkillSource.CORE,
                use_cases=['Validating solutions', 'Finding edge cases', 'Risk assessment']
            ),
            
            # Technical
            SkillMetadata(
                skill_id='code_generation',
                name='Code Generation',
                description='Write correct, efficient, and well-documented code',
                category='technical',
                level='expert',
                source=SkillSource.CORE,
                use_cases=['Implementing features', 'Writing tests', 'Infrastructure setup']
            ),
            SkillMetadata(
                skill_id='debugging',
                name='Debugging',
                description='Systematically identify and fix bugs in code',
                category='technical',
                level='expert',
                source=SkillSource.CORE,
                use_cases=['Fixing errors', 'Performance optimization', 'Root cause analysis']
            ),
            
            # Creative
            SkillMetadata(
                skill_id='innovative_thinking',
                name='Innovative Thinking',
                description='Generate novel solutions to problems',
                category='creative',
                level='advanced',
                source=SkillSource.CORE,
                use_cases=['System design', 'Optimization', 'Novel approaches']
            ),
            
            # Meta
            SkillMetadata(
                skill_id='self_reflection',
                name='Self Reflection',
                description='Analyze own performance and identify improvement areas',
                category='meta',
                level='intermediate',
                source=SkillSource.CORE,
                use_cases=['Learning from failures', 'Process improvement', 'Quality assurance']
            ),
            
            # Communication
            SkillMetadata(
                skill_id='clear_explanation',
                name='Clear Explanation',
                description='Communicate complex ideas clearly and concisely',
                category='communication',
                level='intermediate',
                source=SkillSource.CORE,
                use_cases=['Documentation', 'API design', 'User communication']
            ),
        ]
        
        for skill in core_skills:
            self.skills[skill.skill_id] = skill
        
        logger.info(f"✅ Initialized {len(core_skills)} core skills")
        self._save_registry()
    
    def _load_markdown_skills(self):
        """Scan and load markdown skill files"""
        if not self.skills_dir.exists():
            logger.warning(f"Skills directory not found: {self.skills_dir}")
            logger.info(f"  (This is OK - skills will be loaded from registry only)")
            return
        
        markdown_files = list(self.skills_dir.glob('*.md'))
        if not markdown_files:
            logger.info(f"No markdown skill files found in: {self.skills_dir}")
            return
        
        logger.info(f"Found {len(markdown_files)} markdown skill files")
        
        new_skills = 0
        for md_file in markdown_files:
            skill_metadata = MarkdownSkillParser.parse_skill_file(md_file)
            if skill_metadata:
                # Don't override existing tracked skills
                if skill_metadata.skill_id not in self.skills:
                    self.skills[skill_metadata.skill_id] = skill_metadata
                    new_skills += 1
                else:
                    # Update documentation fields if skill already exists
                    existing = self.skills[skill_metadata.skill_id]
                    existing.use_cases = skill_metadata.use_cases
                    existing.anti_patterns = skill_metadata.anti_patterns
                    existing.prerequisites = skill_metadata.prerequisites
                    existing.related_skills = skill_metadata.related_skills
        
        if new_skills > 0:
            logger.info(f"✅ Loaded {new_skills} new markdown skills")
            self._save_registry()
    
    def _save_registry(self):
        """Save skill registry to disk"""
        try:
            data = {
                skill_id: skill.to_dict()
                for skill_id, skill in self.skills.items()
            }
            with open(self.skills_registry_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            logger.debug(f"Saved {len(data)} skills to registry")
        except Exception as e:
            logger.error(f"Error saving skill registry: {e}")
    
    def refresh_markdown_skills(self) -> Dict[str, Any]:
        """
        Hot-reload markdown skills without restarting the server.
        Rescans the skills directory for new/updated markdown files.
        
        Returns:
            Dictionary with refresh results
        """
        if not self.skills_dir.exists():
            return {"error": f"Skills directory not found: {self.skills_dir}"}
        
        markdown_files = list(self.skills_dir.glob('*.md'))
        initial_count = len(self.skills)
        
        new_skills = 0
        updated_skills = 0
        
        for md_file in markdown_files:
            try:
                skill_metadata = MarkdownSkillParser.parse_skill_file(md_file)
                if skill_metadata:
                    if skill_metadata.skill_id not in self.skills:
                        # New skill
                        self.skills[skill_metadata.skill_id] = skill_metadata
                        new_skills += 1
                        logger.info(f"✅ Added new skill: {skill_metadata.name}")
                    else:
                        # Update existing skill
                        existing = self.skills[skill_metadata.skill_id]
                        existing.use_cases = skill_metadata.use_cases
                        existing.anti_patterns = skill_metadata.anti_patterns
                        existing.prerequisites = skill_metadata.prerequisites
                        existing.related_skills = skill_metadata.related_skills
                        updated_skills += 1
                        logger.info(f"🔄 Updated skill: {skill_metadata.name}")
            except Exception as e:
                logger.error(f"Error parsing {md_file}: {e}")
        
        # Save updated registry
        self._save_registry()
        
        return {
            "success": True,
            "message": f"Skills refreshed: {new_skills} new, {updated_skills} updated",
            "new_skills": new_skills,
            "updated_skills": updated_skills,
            "total_skills": len(self.skills),
            "previous_total": initial_count
        }
    
    def record_skill_usage(self, skill_id: str, success: bool, context: str = "", 
                          details: Optional[Dict[str, Any]] = None) -> bool:
        """
        Record skill usage and update effectiveness
        
        Args:
            skill_id: ID of the skill used
            success: Whether the skill usage was successful
            context: Context of usage (task description, etc)
            details: Additional details about the execution
        
        Returns:
            True if recorded successfully
        """
        if skill_id not in self.skills:
            logger.warning(f"Unknown skill: {skill_id}")
            return False
        
        skill = self.skills[skill_id]
        skill.usage_count += 1
        skill.last_used = datetime.now().isoformat()
        
        if success:
            skill.success_count += 1
        else:
            skill.failure_count += 1
        
        # Recalculate effectiveness score using exponential moving average
        old_effectiveness = skill.effectiveness_score
        new_success_rate = skill.success_rate
        alpha = 0.3  # Smoothing factor
        skill.effectiveness_score = (alpha * new_success_rate) + ((1 - alpha) * old_effectiveness)
        
        logger.info(f"📊 Skill '{skill_id}' usage recorded: {success} | Effectiveness: {skill.effectiveness_score:.2%}")
        
        self._save_registry()
        return True
    
    def get_skill(self, skill_id: str) -> Optional[SkillMetadata]:
        """Get skill metadata by ID"""
        return self.skills.get(skill_id)
    
    def list_skills(self, category: Optional[str] = None, 
                   min_effectiveness: float = 0.0) -> List[SkillMetadata]:
        """
        List skills, optionally filtered
        
        Args:
            category: Filter by category
            min_effectiveness: Minimum effectiveness score (0.0-1.0)
        
        Returns:
            List of matching skills sorted by effectiveness
        """
        skills = list(self.skills.values())
        
        if category:
            skills = [s for s in skills if s.category == category]
        
        if min_effectiveness > 0:
            skills = [s for s in skills if s.effectiveness_score >= min_effectiveness]
        
        # Sort by effectiveness (descending), then by usage (descending)
        return sorted(
            skills,
            key=lambda s: (-s.effectiveness_score, -s.usage_count)
        )
    
    def recommend_skill(self, task_description: str, 
                       category: Optional[str] = None,
                       top_k: int = 3) -> List[Tuple[SkillMetadata, float]]:
        """
        Recommend skills for a task based on effectiveness and relevance
        
        Args:
            task_description: Description of the task
            category: Limit recommendations to category
            top_k: Number of top recommendations
        
        Returns:
            List of (skill, relevance_score) tuples
        """
        # Get candidates
        candidates = self.list_skills(category=category, min_effectiveness=0.5)
        
        if not candidates:
            # Fall back to all skills if no effective ones found
            candidates = self.list_skills(category=category)
        
        # Score based on: effectiveness + usage + keyword matching
        scored = []
        task_lower = task_description.lower()
        
        for skill in candidates:
            # Base score from effectiveness
            score = skill.effectiveness_score
            
            # Boost for usage history
            if skill.usage_count > 0:
                score += 0.1 * min(skill.usage_count / 10, 1.0)
            
            # Boost for keyword matches in use cases
            for use_case in skill.use_cases:
                if any(word in task_lower for word in use_case.lower().split()):
                    score += 0.2
            
            # Penalize for anti-patterns
            for anti_pattern in skill.anti_patterns:
                if any(word in task_lower for word in anti_pattern.lower().split()):
                    score -= 0.3
            
            scored.append((skill, min(score, 1.0)))
        
        # Sort by score and return top K
        return sorted(scored, key=lambda x: -x[1])[:top_k]

    def get_skill_recommendations(self, task: str, limit: int = 3) -> List[Dict[str, Any]]:
        """
        Get skill recommendations (alias for recommend_skill w/ dict return)
        Required by Maintainer Agents.
        """
        recs = self.recommend_skill(task, top_k=limit)
        return [{"skill": s.name, "id": s.skill_id, "score": score, "description": s.description} for s, score in recs]
    
    def export_as_mcp_tools(self) -> List[Dict[str, Any]]:
        """
        Export all skills as MCP tool definitions
        
        Returns:
            List of MCP tool definitions
        """
        return [skill.to_mcp_tool() for skill in self.skills.values()]
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics of all skills"""
        total_skills = len(self.skills)
        by_category = {}
        total_uses = 0
        avg_effectiveness = 0.0
        
        for skill in self.skills.values():
            # Count by category
            cat = skill.category
            by_category[cat] = by_category.get(cat, 0) + 1
            
            # Sum usage and effectiveness
            total_uses += skill.usage_count
            avg_effectiveness += skill.effectiveness_score
        
        avg_effectiveness = avg_effectiveness / total_skills if total_skills > 0 else 0
        
        return {
            'total_skills': total_skills,
            'by_category': by_category,
            'total_uses': total_uses,
            'avg_effectiveness': avg_effectiveness,
            'markdown_skills': sum(1 for s in self.skills.values() if s.source == SkillSource.MARKDOWN),
            'core_skills': sum(1 for s in self.skills.values() if s.source == SkillSource.CORE),
        }


# Global instance
_manager = None


def get_enhanced_skills_manager(data_dir: Path = None, 
                               skills_dir: Path = None) -> EnhancedSkillsManager:
    """Get or create global enhanced skills manager"""
    global _manager
    
    if _manager is None:
        # Default directories with fallbacks
        if data_dir is None:
            # Try common locations in order
            candidates = [
                Path('/app/data/skills'),
                Path('./data/skills'),
                Path(Path.home()) / '.arca' / 'data' / 'skills',
            ]
            for candidate in candidates:
                try:
                    candidate.mkdir(parents=True, exist_ok=True)
                    data_dir = candidate
                    break
                except (PermissionError, OSError):
                    continue
            
            if data_dir is None:
                # Fallback to temp directory
                import tempfile
                data_dir = Path(tempfile.gettempdir()) / 'arca_skills'
                data_dir.mkdir(parents=True, exist_ok=True)
        
        if skills_dir is None:
            # Try common locations for skills
            candidates = [
                Path('/app/skills'),
                Path('./mcp_skills'),
                Path('./services/mcp_server/mcp_skills'),
            ]
            for candidate in candidates:
                if candidate.exists() and candidate.is_dir():
                    skills_dir = candidate
                    break
            
            if skills_dir is None:
                skills_dir = Path('./mcp_skills')  # Default, won't error if doesn't exist
        
        _manager = EnhancedSkillsManager(data_dir, skills_dir)
    
    return _manager


if __name__ == "__main__":
    # Test the manager
    logging.basicConfig(level=logging.INFO)
    
    manager = get_enhanced_skills_manager()
    
    print("\n📚 Enhanced Skills Manager - Test")
    print("=" * 70)
    
    # Summary
    summary = manager.get_summary()
    print(f"\n📊 Summary:")
    print(f"   Total skills: {summary['total_skills']}")
    print(f"   By category: {summary['by_category']}")
    print(f"   Avg effectiveness: {summary['avg_effectiveness']:.2%}")
    
    # Test recommendation
    print(f"\n🔍 Skill Recommendations for 'fix database connection':")
    recommendations = manager.recommend_skill('fix database connection', top_k=3)
    for skill, score in recommendations:
        print(f"   • {skill.name} ({score:.2%} match)")
        print(f"     Use cases: {', '.join(skill.use_cases[:2]) if skill.use_cases else 'N/A'}")
    
    # Test recording usage
    print(f"\n📝 Recording skill usage...")
    if recommendations:
        skill = recommendations[0][0]
        manager.record_skill_usage(skill.skill_id, success=True, context="test")
