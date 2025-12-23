"""
Recipe loader for list crawl mode.

Loads and validates YAML recipe files that define how to crawl
paginated list pages and extract item links.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path
import yaml


@dataclass
class PaginationConfig:
    """Configuration for pagination strategy."""
    type: str  # 'next', 'all_links', or 'url_template'
    next_css: Optional[str] = None
    pagination_scope_css: Optional[str] = None
    page_param: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for passing to extractors."""
        return {
            'type': self.type,
            'next_css': self.next_css,
            'pagination_scope_css': self.pagination_scope_css,
            'page_param': self.page_param,
            'page_start': self.page_start,
            'page_end': self.page_end
        }


@dataclass
class LimitsConfig:
    """Configuration for crawl limits."""
    max_list_pages: Optional[int] = None
    max_items: Optional[int] = None


@dataclass
class OutputConfig:
    """Configuration for output files."""
    items_jsonl: str = "output/items.jsonl"
    pages_jsonl: str = "output/list_pages.jsonl"


@dataclass
class Recipe:
    """
    Complete recipe configuration for list crawl mode.

    Defines how to crawl a paginated list and extract item links.
    """
    start_urls: List[str]
    list_scope_css: str
    item_link_css: str = "a[href]"
    pagination: Optional[PaginationConfig] = None
    limits: LimitsConfig = field(default_factory=LimitsConfig)
    output: OutputConfig = field(default_factory=OutputConfig)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Recipe':
        """
        Create a Recipe from a dictionary (loaded from YAML).

        Args:
            data: Dictionary from YAML file

        Returns:
            Recipe instance

        Raises:
            ValueError: If required fields are missing or invalid
        """
        # Validate required fields
        if 'start_urls' not in data:
            raise ValueError("Recipe must have 'start_urls' field")
        if 'list_scope_css' not in data:
            raise ValueError("Recipe must have 'list_scope_css' field")

        start_urls = data['start_urls']
        if not isinstance(start_urls, list) or not start_urls:
            raise ValueError("'start_urls' must be a non-empty list")

        list_scope_css = data['list_scope_css']
        if not isinstance(list_scope_css, str) or not list_scope_css.strip():
            raise ValueError("'list_scope_css' must be a non-empty string")

        # Optional fields with defaults
        item_link_css = data.get('item_link_css', 'a[href]')

        # Parse pagination config
        pagination = None
        if 'pagination' in data:
            pagination_data = data['pagination']
            if not isinstance(pagination_data, dict):
                raise ValueError("'pagination' must be a dictionary")

            pagination_type = pagination_data.get('type')
            if not pagination_type:
                raise ValueError("'pagination.type' is required")

            if pagination_type not in ['next', 'all_links', 'url_template']:
                raise ValueError(f"Invalid pagination type: {pagination_type}")

            # Validate type-specific fields
            if pagination_type == 'next' and 'next_css' not in pagination_data:
                raise ValueError("'pagination.next_css' is required for type 'next'")

            if pagination_type == 'all_links' and 'pagination_scope_css' not in pagination_data:
                raise ValueError("'pagination.pagination_scope_css' is required for type 'all_links'")

            if pagination_type == 'url_template':
                if 'page_param' not in pagination_data:
                    raise ValueError("'pagination.page_param' is required for type 'url_template'")
                if 'page_start' not in pagination_data:
                    raise ValueError("'pagination.page_start' is required for type 'url_template'")
                if 'page_end' not in pagination_data:
                    raise ValueError("'pagination.page_end' is required for type 'url_template'")

            pagination = PaginationConfig(
                type=pagination_type,
                next_css=pagination_data.get('next_css'),
                pagination_scope_css=pagination_data.get('pagination_scope_css'),
                page_param=pagination_data.get('page_param'),
                page_start=pagination_data.get('page_start'),
                page_end=pagination_data.get('page_end')
            )

        # Parse limits config
        limits = LimitsConfig()
        if 'limits' in data:
            limits_data = data['limits']
            if isinstance(limits_data, dict):
                limits.max_list_pages = limits_data.get('max_list_pages')
                limits.max_items = limits_data.get('max_items')

        # Parse output config
        output = OutputConfig()
        if 'output' in data:
            output_data = data['output']
            if isinstance(output_data, dict):
                output.items_jsonl = output_data.get('items_jsonl', output.items_jsonl)
                output.pages_jsonl = output_data.get('pages_jsonl', output.pages_jsonl)

        return cls(
            start_urls=start_urls,
            list_scope_css=list_scope_css,
            item_link_css=item_link_css,
            pagination=pagination,
            limits=limits,
            output=output
        )


def load_recipe(file_path: str) -> Recipe:
    """
    Load a recipe from a YAML file.

    Args:
        file_path: Path to YAML recipe file

    Returns:
        Recipe instance

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If recipe is invalid
        yaml.YAMLError: If YAML parsing fails
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Recipe file not found: {file_path}")

    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError("Recipe file must contain a YAML dictionary")

    return Recipe.from_dict(data)


def validate_recipe(recipe: Recipe) -> List[str]:
    """
    Validate a recipe and return a list of warnings (not errors).

    Args:
        recipe: Recipe to validate

    Returns:
        List of warning messages (empty if no warnings)
    """
    warnings = []

    # Check if URLs are valid
    for url in recipe.start_urls:
        if not url.startswith('http://') and not url.startswith('https://'):
            warnings.append(f"URL may be invalid (missing http/https): {url}")

    # Check if limits are reasonable
    if recipe.limits.max_list_pages and recipe.limits.max_list_pages > 1000:
        warnings.append(f"max_list_pages is very high: {recipe.limits.max_list_pages}")

    if recipe.limits.max_items and recipe.limits.max_items > 10000:
        warnings.append(f"max_items is very high: {recipe.limits.max_items}")

    # Check if pagination is configured
    if recipe.pagination is None:
        warnings.append("No pagination configured - will only crawl start_urls")

    return warnings

