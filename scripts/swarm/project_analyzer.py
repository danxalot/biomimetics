#!/usr/bin/env python3
"""
Multi-Model Project Analyzer
============================
Orchestrates Serena MCP across multiple models to perform comprehensive
project analysis. Each model finds different issues (as demonstrated
by Kilo Code's multi-model discovery).

Usage:
    python project_analyzer.py --mode full|quick|deep
"""

import asyncio
import json
import subprocess
import sys
import os
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from model_selector import MODEL_MATRIX, ModelRouter, TaskType, ModelTier


@dataclass
class AnalysisResult:
    model_name: str
    model_id: str
    findings: List[Dict]
    errors: List[str]
    suggestions: List[str]
    timestamp: str


class MultiModelAnalyzer:
    """
    Coordinates Serena MCP across multiple models for comprehensive analysis.
    Each model contributes unique perspectives based on its strengths.
    """

    def __init__(self, project_path: str = "/Users/danexall/biomimetics"):
        self.project_path = project_path
        self.router = ModelRouter()
        self.results: List[AnalysisResult] = []

    def get_analysis_prompts(self) -> Dict[str, str]:
        """Generate specialized prompts for each model's strengths."""
        return {
            "architecture": """Analyze the project architecture. Focus on:
- Component relationships and dependencies
- Design pattern usage
- Scalability considerations
- Technical debt indicators""",
            "code_quality": """Analyze code quality. Focus on:
- Code smells and anti-patterns
- Error handling robustness
- Type safety and contract enforcement
- Performance optimization opportunities""",
            "security": """Analyze security posture. Focus on:
- Authentication/authorization patterns
- Input validation
- Secrets management
- Potential vulnerabilities""",
            "errors": """Perform error analysis. Focus on:
- Exception handling completeness
- Error propagation patterns
- Edge case coverage
- Failure mode analysis""",
            "integration": """Analyze integration points. Focus on:
- API contracts and versioning
- External service dependencies
- Data flow between components
- Error recovery mechanisms""",
            "testing": """Analyze test coverage. Focus on:
- Unit test coverage gaps
- Integration test completeness
- Edge case testing
- Test maintainability""",
        }

    async def analyze_with_model(
        self, model_id: str, focus_area: str = "full"
    ) -> AnalysisResult:
        """Run Serena MCP analysis with specific model."""
        model = MODEL_MATRIX.get(model_id)
        if not model:
            return AnalysisResult(
                model_name="Unknown",
                model_id=model_id,
                findings=[],
                errors=[f"Model {model_id} not found"],
                suggestions=[],
                timestamp=datetime.now().isoformat(),
            )

        prompt = self.get_analysis_prompts().get(
            focus_area, self.get_analysis_prompts()["architecture"]
        )

        command = [
            "uvx",
            "--from",
            "git+https://github.com/oraios/serena",
            "serena",
            "analyze",
            self.project_path,
            "--prompt",
            prompt,
            "--model",
            model_id,
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=self.project_path,
            )

            return AnalysisResult(
                model_name=model.name,
                model_id=model_id,
                findings=self._parse_findings(result.stdout),
                errors=self._parse_errors(result.stderr),
                suggestions=self._parse_suggestions(result.stdout),
                timestamp=datetime.now().isoformat(),
            )
        except subprocess.TimeoutExpired:
            return AnalysisResult(
                model_name=model.name,
                model_id=model_id,
                findings=[],
                errors=["Analysis timed out after 5 minutes"],
                suggestions=[],
                timestamp=datetime.now().isoformat(),
            )
        except Exception as e:
            return AnalysisResult(
                model_name=model.name,
                model_id=model_id,
                findings=[],
                errors=[str(e)],
                suggestions=[],
                timestamp=datetime.now().isoformat(),
            )

    def _parse_findings(self, output: str) -> List[Dict]:
        try:
            data = json.loads(output)
            return data.get("findings", [])
        except:
            return [{"type": "general", "content": output[:500]}]

    def _parse_errors(self, stderr: str) -> List[str]:
        if not stderr:
            return []
        return [line for line in stderr.split("\n") if line.strip()]

    def _parse_suggestions(self, output: str) -> List[str]:
        try:
            data = json.loads(output)
            return data.get("suggestions", [])
        except:
            return []

    async def run_full_analysis(self) -> List[AnalysisResult]:
        """
        Run comprehensive multi-model analysis.
        Each model contributes its unique perspective.
        """
        team = self.router.get_project_analysis_team()

        print("=" * 70)
        print("MULTI-MODEL PROJECT ANALYSIS")
        print("=" * 70)
        print(f"Project: {self.project_path}")
        print(f"Analysis Team: {[m.name for m in team]}")
        print("=" * 70)

        tasks = []
        for model in team:
            print(f"\n[+] Deploying {model.name}...")
            task = self.analyze_with_model(model.id, focus_area="full")
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.results.append(
                    AnalysisResult(
                        model_name=team[i].name,
                        model_id=team[i].id,
                        findings=[],
                        errors=[str(result)],
                        suggestions=[],
                        timestamp=datetime.now().isoformat(),
                    )
                )
            else:
                self.results.append(result)

        return self.results

    async def run_targeted_analysis(self, focus_area: str) -> List[AnalysisResult]:
        """Run analysis focused on specific area."""
        model = self.router.select_model(TaskType.ANALYSIS)
        result = await self.analyze_with_model(model.id, focus_area=focus_area)
        self.results.append(result)
        return [result]

    def generate_report(self) -> str:
        """Generate consolidated analysis report."""
        report = []
        report.append("=" * 70)
        report.append("TONY STARK SWARM - CONSOLIDATED ANALYSIS REPORT")
        report.append("=" * 70)
        report.append(f"Generated: {datetime.now().isoformat()}")
        report.append("")

        all_findings = []
        all_suggestions = []

        for result in self.results:
            report.append(f"\n## {result.model_name}")
            report.append("-" * 50)

            if result.findings:
                report.append(f"\nFindings ({len(result.findings)}):")
                for finding in result.findings[:10]:
                    all_findings.append(finding)
                    report.append(
                        f"  - [{finding.get('severity', 'info')}] {finding.get('content', finding)}"
                    )

            if result.errors:
                report.append(f"\nErrors ({len(result.errors)}):")
                for error in result.errors[:5]:
                    report.append(f"  - {error}")

            if result.suggestions:
                report.append(f"\nSuggestions ({len(result.suggestions)}):")
                for suggestion in result.suggestions[:5]:
                    all_suggestions.append(suggestion)
                    report.append(f"  - {suggestion}")

        report.append("\n" + "=" * 70)
        report.append("CONSOLIDATED RECOMMENDATIONS")
        report.append("=" * 70)
        report.append(f"\nTotal Findings: {len(all_findings)}")
        report.append(f"Total Suggestions: {len(all_suggestions)}")

        return "\n".join(report)

    def save_report(self, filename: str = None):
        """Save analysis report to file."""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            filename = f"analysis-{timestamp}.md"

        report_path = os.path.join(self.project_path, "logs", filename)
        os.makedirs(os.path.dirname(report_path), exist_ok=True)

        with open(report_path, "w") as f:
            f.write(self.generate_report())

        print(f"\n[+] Report saved to: {report_path}")
        return report_path


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Multi-Model Project Analyzer")
    parser.add_argument(
        "--mode",
        choices=["full", "quick", "deep", "architecture", "security"],
        default="full",
        help="Analysis mode",
    )
    parser.add_argument(
        "--project",
        default="/Users/danexall/biomimetics",
        help="Project path to analyze",
    )
    parser.add_argument("--output", help="Output file path")
    args = parser.parse_args()

    analyzer = MultiModelAnalyzer(project_path=args.project)

    if args.mode == "full":
        await analyzer.run_full_analysis()
    elif args.mode == "quick":
        await analyzer.run_targeted_analysis("code_quality")
    elif args.mode == "deep":
        team = analyzer.router.get_project_analysis_team()
        for model in team[:2]:
            await analyzer.analyze_with_model(model.id, focus_area="full")
    else:
        await analyzer.run_targeted_analysis(args.mode)

    report = analyzer.generate_report()
    print(report)

    if args.output:
        analyzer.save_report(args.output)

    return analyzer.results


if __name__ == "__main__":
    asyncio.run(main())
