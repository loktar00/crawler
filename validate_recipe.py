"""
Simple script to validate a recipe file.

Usage:
    python validate_recipe.py recipes/example_quotes.yaml
"""

import sys
import logging
from pathlib import Path

from recipe_loader import load_recipe, validate_recipe

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def main():
    if len(sys.argv) < 2:
        print("Usage: python validate_recipe.py <recipe_file>")
        sys.exit(1)

    recipe_file = sys.argv[1]

    try:
        logger.info(f"Loading recipe: {recipe_file}")
        recipe = load_recipe(recipe_file)

        logger.info("✓ Recipe loaded successfully")
        logger.info(f"  Start URLs: {len(recipe.start_urls)}")
        for url in recipe.start_urls:
            logger.info(f"    - {url}")

        logger.info(f"  List scope CSS: {recipe.list_scope_css}")
        logger.info(f"  Item link CSS: {recipe.item_link_css}")

        if recipe.pagination:
            logger.info(f"  Pagination type: {recipe.pagination.type}")
            if recipe.pagination.type == 'next':
                logger.info(f"    Next CSS: {recipe.pagination.next_css}")
            elif recipe.pagination.type == 'all_links':
                logger.info(f"    Scope CSS: {recipe.pagination.pagination_scope_css}")
            elif recipe.pagination.type == 'url_template':
                logger.info(f"    Param: {recipe.pagination.page_param}")
                logger.info(f"    Range: {recipe.pagination.page_start}-{recipe.pagination.page_end}")
        else:
            logger.info("  Pagination: None")

        if recipe.limits.max_list_pages:
            logger.info(f"  Max list pages: {recipe.limits.max_list_pages}")
        if recipe.limits.max_items:
            logger.info(f"  Max items: {recipe.limits.max_items}")

        logger.info(f"  Output items: {recipe.output.items_jsonl}")
        logger.info(f"  Output pages: {recipe.output.pages_jsonl}")

        # Validate
        warnings = validate_recipe(recipe)
        if warnings:
            logger.warning("Validation warnings:")
            for warning in warnings:
                logger.warning(f"  - {warning}")
        else:
            logger.info("✓ No validation warnings")

        logger.info("")
        logger.info("Recipe is valid and ready to use!")
        logger.info(f"Run with: python crawler.py --mode list --recipe {recipe_file}")

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        sys.exit(1)
    except ValueError as e:
        logger.error(f"Invalid recipe: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

