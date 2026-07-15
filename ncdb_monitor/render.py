import logging

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | "
        "%(levelname)-8s | "
        "%(name)s | "
        "%(message)s"
    )
)

import os
import json

from pathlib import Path

from jinja2 import (
    Environment,
    FileSystemLoader
)

from ncdb_monitor.config import WEBSITE_DATA_FILE


BASE_DIR = Path(__file__).parent

TEMPLATE_DIR = BASE_DIR / "templates"


def render_template(
    env,
    template_name,
    output_file,
    **context
):

    template = env.get_template(
        template_name
    )

    html = template.render(**context)

    logger.debug(
        f"Writing {output_file}"
    )

    with open(output_file, "w") as f:

        f.write(html)


def generate_html(website_dir):

    logger.info(
        f"generate_html in "
        f"{website_dir}"
    )

    website_data_file = (
        website_dir / WEBSITE_DATA_FILE
    )

    with open(website_data_file) as f:

        website_data = json.load(f)

    env = Environment(
        loader=FileSystemLoader(
            TEMPLATE_DIR
        )
    )

    #
    # Main index page
    #

    render_template(
        env,
        "index.html",
        os.path.join(
            website_dir,
            "index.html"
        ),
        website=website_data
    )

    #
    # Obsspace pages
    #

    for dataset in website_data["datasets"]:

        dataset_dir_name = dataset["dir_name"]

        for obsspace in dataset["obsspaces"]:

            obsspace_safe_name = (
                obsspace["safe_name"]
            )

            obsspace_dir = os.path.join(
                website_dir,
                dataset_dir_name,
                obsspace_safe_name
            )

            os.makedirs(
                obsspace_dir,
                exist_ok=True
            )

            render_template(
                env,
                "obsspace.html",
                os.path.join(
                    obsspace_dir,
                    "index.html"
                ),
                website=website_data,
                dataset=dataset,
                obsspace=obsspace
            )

