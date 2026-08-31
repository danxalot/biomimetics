"""
MCP Skill Tools Integration

Exposes the enhanced skills framework as MCP tools that all agents can call:
- list_skills: List available skills with effectiveness metrics
- get_skill_details: Get detailed metadata for a skill
- recommend_skills: Get skill recommendations for a task
- select_skill_for_task: Select best skill (uses SkillSelectionAgent)
- rate_skill_execution: Record skill usage and update effectiveness

These tools bridge the enhanced skills manager and MCP protocol.
"""

import logging
import json
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Import the managers
try:
    from enhanced_skills_manager import get_enhanced_skills_manager, SkillSource
    from skill_selection_agent import get_skill_selection_agent
except ImportError:
    # Handle import during development
    from services.mcp_server.enhanced_skills_manager import get_enhanced_skills_manager, SkillSource
    from services.mcp_server.skill_selection_agent import get_skill_selection_agent


class SkillToolsRegistry:
    """Registry of MCP tools for skills management"""
    
    def __init__(self):
        self.skills_manager = get_enhanced_skills_manager()
        self.selection_agent = get_skill_selection_agent(self.skills_manager)
        self.tools = self._initialize_tools()
    
    def _initialize_tools(self) -> Dict[str, Dict[str, Any]]:
        """Initialize MCP tool definitions"""
        return {
            'list_skills': {
                'name': 'list_skills',
                'description': 'List available skills with effectiveness metrics and metadata',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'category': {
                            'type': 'string',
                            'description': 'Filter by category: reasoning, technical, creative, meta, communication (optional)',
                            'enum': ['reasoning', 'technical', 'creative', 'meta', 'communication']
                        },
                        'min_effectiveness': {
                            'type': 'number',
                            'description': 'Minimum effectiveness score (0.0-1.0), default 0.0',
                            'default': 0.0
                        },
                        'sort_by': {
                            'type': 'string',
                            'description': 'Sort by: effectiveness, usage, name',
                            'enum': ['effectiveness', 'usage', 'name'],
                            'default': 'effectiveness'
                        }
                    }
                }
            },
            'get_skill_details': {
                'name': 'get_skill_details',
                'description': 'Get detailed metadata and documentation for a specific skill',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'skill_id': {
                            'type': 'string',
                            'description': 'ID of the skill (e.g., "logical_analysis", "code_generation")'
                        }
                    },
                    'required': ['skill_id']
                }
            },
            'recommend_skills': {
                'name': 'recommend_skills',
                'description': 'Get skill recommendations for a specific task, ranked by effectiveness',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'task_description': {
                            'type': 'string',
                            'description': 'Description of what you want to accomplish'
                        },
                        'category': {
                            'type': 'string',
                            'description': 'Optionally limit to specific category',
                            'enum': ['reasoning', 'technical', 'creative', 'meta', 'communication']
                        },
                        'top_k': {
                            'type': 'integer',
                            'description': 'Number of recommendations (default 3)',
                            'default': 3
                        }
                    },
                    'required': ['task_description']
                }
            },
            'select_skill_for_task': {
                'name': 'select_skill_for_task',
                'description': 'Use intelligent skill selection agent to select best skill for task',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'task_description': {
                            'type': 'string',
                            'description': 'Description of the task to be performed'
                        },
                        'category': {
                            'type': 'string',
                            'description': 'Optional category restriction',
                            'enum': ['reasoning', 'technical', 'creative', 'meta', 'communication']
                        },
                        'strategy': {
                            'type': 'string',
                            'description': 'Selection strategy: best_match, highest_effectiveness, balanced, learning',
                            'enum': ['best_match', 'highest_effectiveness', 'balanced', 'learning'],
                            'default': 'balanced'
                        }
                    },
                    'required': ['task_description']
                }
            },
            'rate_skill_execution': {
                'name': 'rate_skill_execution',
                'description': 'Record skill usage and effectiveness rating (updates system learning)',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'skill_id': {
                            'type': 'string',
                            'description': 'ID of the skill that was used'
                        },
                        'success': {
                            'type': 'boolean',
                            'description': 'Whether the skill execution was successful'
                        },
                        'context': {
                            'type': 'string',
                            'description': 'Context of usage (optional)',
                            'default': ''
                        },
                        'details': {
                            'type': 'object',
                            'description': 'Additional details about execution (optional)',
                            'default': {}
                        }
                    },
                    'required': ['skill_id', 'success']
                }
            },
            'get_skills_summary': {
                'name': 'get_skills_summary',
                'description': 'Get summary statistics of all available skills',
                'inputSchema': {
                    'type': 'object',
                    'properties': {}
                }
            }
        }
    
    def list_skills(self, category: Optional[str] = None, 
                    min_effectiveness: float = 0.0,
                    sort_by: str = 'effectiveness') -> Dict[str, Any]:
        """List skills with optional filtering"""
        skills = self.skills_manager.list_skills(category=category, min_effectiveness=min_effectiveness)
        
        # Sort if requested
        if sort_by == 'usage':
            skills.sort(key=lambda s: -s.usage_count)
        elif sort_by == 'name':
            skills.sort(key=lambda s: s.name)
        # else: already sorted by effectiveness
        
        return {
            'total': len(skills),
            'category_filter': category,
            'min_effectiveness': min_effectiveness,
            'skills': [
                {
                    'id': s.skill_id,
                    'name': s.name,
                    'category': s.category,
                    'level': s.level,
                    'effectiveness': f"{s.effectiveness_score:.2%}",
                    'success_rate': f"{s.success_rate:.2%}",
                    'usage_count': s.usage_count,
                    'source': s.source.value,
                    'recommended': s.recommended,
                    'last_used': s.last_used,
                }
                for s in skills
            ]
        }
    
    def get_skill_details(self, skill_id: str) -> Dict[str, Any]:
        """Get detailed skill information"""
        skill = self.skills_manager.get_skill(skill_id)
        
        if not skill:
            return {
                'error': f"Skill not found: {skill_id}",
                'available_skills': [s.skill_id for s in self.skills_manager.skills.values()][:10]
            }
        
        return {
            'id': skill.skill_id,
            'name': skill.name,
            'description': skill.description,
            'category': skill.category,
            'level': skill.level,
            'source': skill.source.value,
            'effectiveness': {
                'score': f"{skill.effectiveness_score:.2%}",
                'success_rate': f"{skill.success_rate:.2%}",
                'usage_count': skill.usage_count,
                'success_count': skill.success_count,
                'failure_count': skill.failure_count,
                'last_used': skill.last_used,
                'recommended': skill.recommended
            },
            'documentation': {
                'parameters': skill.parameters,
                'returns': skill.returns,
                'use_cases': skill.use_cases,
                'anti_patterns': skill.anti_patterns,
                'prerequisites': skill.prerequisites,
                'related_skills': skill.related_skills
            },
            'learning': {
                'weaknesses': skill.weaknesses,
                'improvements': skill.improvements,
                'needs_improvement': skill.needs_improvement
            }
        }
    
    def recommend_skills(self, task_description: str,
                        category: Optional[str] = None,
                        top_k: int = 3) -> Dict[str, Any]:
        """Get skill recommendations for a task"""
        recommendations = self.skills_manager.recommend_skill(
            task_description,
            category=category,
            top_k=top_k
        )
        
        if not recommendations:
            return {
                'task': task_description,
                'recommendations': [],
                'message': 'No skills available for this task'
            }
        
        return {
            'task': task_description,
            'category_filter': category,
            'recommendations': [
                {
                    'rank': i + 1,
                    'skill_id': skill.skill_id,
                    'skill_name': skill.name,
                    'category': skill.category,
                    'relevance_score': f"{score:.2%}",
                    'effectiveness': f"{skill.effectiveness_score:.2%}",
                    'success_rate': f"{skill.success_rate:.2%}",
                    'usage_count': skill.usage_count,
                    'use_cases': skill.use_cases[:3],  # Top 3 use cases
                }
                for i, (skill, score) in enumerate(recommendations)
            ]
        }
    
    def select_skill_for_task(self, task_description: str,
                             category: Optional[str] = None,
                             strategy: str = 'balanced') -> Dict[str, Any]:
        """Use intelligent agent to select best skill"""
        try:
            from services.mcp_server.skill_selection_agent import SelectionStrategy
        except ImportError:
            try:
                from skill_selection_agent import SelectionStrategy
            except ImportError:
                return {'error': "Could not import SelectionStrategy"}
        
        try:
            strategy_enum = SelectionStrategy(strategy)
        except ValueError:
            return {'error': f"Invalid strategy: {strategy}"}
        
        selection = self.selection_agent.select_skill(
            task_description,
            category=category,
            strategy=strategy_enum
        )
        
        if not selection:
            return {
                'task': task_description,
                'error': 'No suitable skill found for this task'
            }
        
        return {
            'task': task_description,
            'selection': {
                'selected_skill_id': selection.selected_skill_id,
                'selected_skill_name': selection.skill_name,
                'effectiveness': f"{selection.effectiveness:.2%}",
                'confidence': f"{selection.confidence:.2%}",
                'reasoning': selection.reasoning,
                'estimated_success_rate': f"{selection.estimated_success_rate:.2%}",
                'required_parameters': selection.required_parameters
            },
            'alternatives': [
                {
                    'skill_id': alt[0],
                    'skill_name': alt[1],
                    'score': f"{alt[2]:.2%}"
                }
                for alt in selection.alternatives
            ]
        }
    
    def rate_skill_execution(self, skill_id: str, success: bool,
                            context: str = "", details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Record skill usage and update effectiveness"""
        success_indicator = "✅" if success else "❌"
        
        result = self.skills_manager.record_skill_usage(
            skill_id,
            success=success,
            context=context,
            details=details
        )
        
        if not result:
            return {'error': f"Unknown skill: {skill_id}"}
        
        skill = self.skills_manager.get_skill(skill_id)
        
        return {
            'skill_id': skill_id,
            'skill_name': skill.name,
            'recorded': True,
            'execution_status': f"{success_indicator} {'Success' if success else 'Failure'}",
            'updated_effectiveness': {
                'score': f"{skill.effectiveness_score:.2%}",
                'success_rate': f"{skill.success_rate:.2%}",
                'total_usage': skill.usage_count,
                'success_count': skill.success_count,
                'failure_count': skill.failure_count
            }
        }
    
    def get_skills_summary(self) -> Dict[str, Any]:
        """Get summary statistics"""
        summary = self.skills_manager.get_summary()
        
        return {
            'total_skills': summary['total_skills'],
            'by_source': {
                'core': summary['core_skills'],
                'markdown': summary['markdown_skills'],
            },
            'by_category': summary['by_category'],
            'total_usage': summary['total_uses'],
            'average_effectiveness': f"{summary['avg_effectiveness']:.2%}",
            'selection_agent': {
                'total_selections': self.selection_agent.stats['total_selections'],
                'successful_executions': self.selection_agent.stats['successful_executions'],
                'failed_executions': self.selection_agent.stats['failed_executions'],
                'success_rate': f"{self.selection_agent.stats['successful_executions'] / max(self.selection_agent.stats['successful_executions'] + self.selection_agent.stats['failed_executions'], 1):.2%}",
                'avg_confidence': f"{self.selection_agent.stats['avg_confidence']:.2%}",
            }
        }
    
    def call_tool(self, tool_name: str, parameters: Dict[str, Any]) -> str:
        """Call a tool and return JSON result"""
        try:
            if tool_name == 'list_skills':
                result = self.list_skills(
                    category=parameters.get('category'),
                    min_effectiveness=parameters.get('min_effectiveness', 0.0),
                    sort_by=parameters.get('sort_by', 'effectiveness')
                )
            
            elif tool_name == 'get_skill_details':
                result = self.get_skill_details(parameters['skill_id'])
            
            elif tool_name == 'recommend_skills':
                result = self.recommend_skills(
                    parameters['task_description'],
                    category=parameters.get('category'),
                    top_k=parameters.get('top_k', 3)
                )
            
            elif tool_name == 'select_skill_for_task':
                result = self.select_skill_for_task(
                    parameters['task_description'],
                    category=parameters.get('category'),
                    strategy=parameters.get('strategy', 'balanced')
                )
            
            elif tool_name == 'rate_skill_execution':
                result = self.rate_skill_execution(
                    parameters['skill_id'],
                    parameters['success'],
                    context=parameters.get('context', ''),
                    details=parameters.get('details')
                )
            
            elif tool_name == 'get_skills_summary':
                result = self.get_skills_summary()
            
            else:
                result = {'error': f"Unknown tool: {tool_name}"}
            
            return json.dumps(result, indent=2)
        
        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}", exc_info=True)
            return json.dumps({'error': str(e)})
    
    def get_tools_list(self) -> List[Dict[str, Any]]:
        """Get list of available tools for MCP"""
        return list(self.tools.values())


# Global registry instance
_registry = None


def get_skill_tools_registry() -> SkillToolsRegistry:
    """Get or create global skill tools registry"""
    global _registry
    
    if _registry is None:
        _registry = SkillToolsRegistry()
    
    return _registry


if __name__ == "__main__":
    # Test the registry
    logging.basicConfig(level=logging.INFO)
    
    print("\n🛠️  Skill Tools Registry - Test")
    print("=" * 70)
    
    registry = get_skill_tools_registry()
    
    # Show available tools
    print("\n📋 Available Tools:")
    for tool in registry.get_tools_list():
        print(f"   • {tool['name']}: {tool['description'][:50]}...")
    
    # Test list_skills
    print("\n🔍 Testing list_skills:")
    result = registry.call_tool('list_skills', {'category': 'reasoning', 'min_effectiveness': 0.5})
    data = json.loads(result)
    print(f"   Found {data['total']} reasoning skills")
    
    # Test recommend_skills
    print("\n🎯 Testing recommend_skills:")
    result = registry.call_tool('recommend_skills', {
        'task_description': 'Debug a complex database query performance issue'
    })
    data = json.loads(result)
    print(f"   Found {len(data['recommendations'])} recommendations")
    for rec in data['recommendations'][:3]:
        print(f"      • {rec['skill_name']} ({rec['relevance_score']})")
    
    # Test summary
    print("\n📊 Testing get_skills_summary:")
    result = registry.call_tool('get_skills_summary', {})
    data = json.loads(result)
    print(f"   Total skills: {data['total_skills']}")
    print(f"   Average effectiveness: {data['average_effectiveness']}")
    print(f"   By category: {data['by_category']}")
