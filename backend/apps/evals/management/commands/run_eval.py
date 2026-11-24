from django.core.management.base import BaseCommand

from apps.jobs.formats import FORMATS
from apps.evals.models import EvalArticle
from apps.evals.services.runner import run_eval


class Command(BaseCommand):
    help = "Run a factual accuracy evaluation with real LLM calls."

    def add_arguments(self, parser):
        parser.add_argument(
            "--model", required=True,
            help="Generation model to evaluate (e.g. gemini-2.5-flash)",
        )
        parser.add_argument(
            "--judge-model", default="gemini-2.5-flash",
            help="Model used as LLM-as-judge (default: gemini-2.5-flash)",
        )
        parser.add_argument(
            "--articles", type=int, default=0,
            help="Limit to N random articles (0 = all)",
        )
        parser.add_argument(
            "--formats", type=str, default="",
            help="Comma-separated format keys (default: all)",
        )

    def handle(self, *args, **options):
        articles = EvalArticle.objects.all()
        if not articles.exists():
            self.stderr.write(
                "No eval articles found. Load them first:\n"
                "  python manage.py loaddata eval_articles\n"
            )
            return

        limit = options["articles"]
        if limit > 0:
            articles = articles.order_by("?")[:limit]

        formats = None
        if options["formats"]:
            formats = [f.strip() for f in options["formats"].split(",")]
            invalid = [f for f in formats if f not in FORMATS]
            if invalid:
                self.stderr.write(f"Unknown formats: {', '.join(invalid)}")
                self.stderr.write(f"Available: {', '.join(FORMATS.keys())}")
                return

        run = run_eval(
            model=options["model"],
            judge_model=options["judge_model"],
            articles=articles,
            formats=formats,
            stdout=self.stdout.write,
        )

        self.stdout.write(f"\nRun ID: {run.id}")
        self.stdout.write(f"Status: {run.status}")
