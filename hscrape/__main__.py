import argparse
import os
from pathlib import Path
import re
from typing import List

import requests
from rich.console import Console, themes
from rich.progress import track

COMMIT_SEARCH_URL = "https://api.github.com/search/commits?q=owner%3A{}+{}"
DIFF_URL = "https://github.com/{}/commit/{}.diff"
REGEX = r"^(?=.*(?:{})).*"

curr_dir = Path(__file__).parent.resolve()
console = Console(
    theme=themes.Theme(
        {"info": "blue", "success": "green", "warning": "yellow", "error": "red"}
    )
)


def verbose_print(message: str):
    if is_verbose:
        console.print(message)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="A Simple POC of a web scraper to demonstrate careless use of GitHub"
    )
    parser.add_argument(
        "--user", "-u", required=True, help="The GitHub username to search for"
    )
    parser.add_argument(
        "--query-wordlists",
        "-q",
        nargs="+",
        default=[
            curr_dir / "wordlists" / "sensitive_filenames.txt",
            curr_dir / "wordlists" / "sensitive_keywords.txt",
        ],
        type=List[Path],
        help="A list of commit messages to search for",
    )

    parser.add_argument(
        "--terms",
        "-t",
        nargs="+",
        default=["mongodb"],
        type=str,
        help="A list of terms to search for in  the commits",
    )

    parser.add_argument("--output", "-o", help="Output files path")

    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose mode"
    )

    args = parser.parse_args()

    username = args.user
    output_dir: str | None = args.output
    query_wordlists: list[Path] = args.query_wordlists
    terms: list[str] = args.terms
    is_verbose: bool = args.verbose

    return (username, output_dir, query_wordlists, terms, is_verbose)


def query_commits(username: str, query: str, output_dir: str | None) -> list[str]:
    url = COMMIT_SEARCH_URL.format(username, query.replace(" ", "+"))
    verbose_print(f"searching: {url}")

    response = requests.get(url)

    if response.status_code != requests.codes.ok:
        console.print(
            f"[!] Request failed with status code {response.status_code}", style="error"
        )
        verbose_print(response.text)

        return []

    data = response.json()

    commits = list(map(extract_commit_details, data["items"]))

    commit_diffs = map(
        lambda commit: get_commit_diff(commit[0], commit[1], output_dir),
        track(
            commits,
            disable=is_verbose,
            description=f'Searching for "{query}"',
        ),
    )

    contents = [diff for diff in commit_diffs if diff is not None]

    console.print(f"Managed to grab {len(contents)} commits!\n")

    return contents


def get_commit_diff(repository: str, commit_hash: str, output_dir: str | None):
    url = DIFF_URL.format(repository, commit_hash)

    try:
        response = requests.get(url)
        response.raise_for_status()

        if output_dir is None:
            verbose_print(f"[+] found {url}")
        else:
            file_path = os.path.join(
                output_dir, f"{repository.replace('/', '_')}_{commit_hash}.txt"
            )

            if os.path.exists(file_path):
                verbose_print(f"[ ] found already existing {url}")
            else:
                with open(file_path, "w") as json_file:
                    json_file.write(response.text)

                verbose_print(f"[+] grabbed {url}")

        return response.text
    except Exception as e:
        console.print(f"[!] couldn't reach {url}", style="error")


def extract_commit_details(item):
    repository = item["repository"]["full_name"]
    commit_hash = item["sha"]

    return repository, commit_hash


def search_terms_in_commit(content: str, terms: list[str]):
    lines = content.split("\n")

    return list(
        filter(lambda line: re.search(REGEX.format("|".join(terms)), line), lines)
    )


def main():
    username, output_dir, query_wordlist_paths, terms, verbose_mode = parse_arguments()

    global is_verbose
    is_verbose = verbose_mode

    # Load query wordlist
    query_wordlist = []
    for wordlist_path in query_wordlist_paths:
        with open(wordlist_path, "r") as f:
            query_wordlist.extend(f.read().splitlines())

    console.print(
        f"Loaded {len(query_wordlist)} query terms from {len(query_wordlist_paths)} wordlists.",
        style="success",
    )

    query_results = list(
        map(
            lambda wordlist: query_commits(username, wordlist, output_dir),
            query_wordlist,
        )
    )

    # if terms is not None:
    #     for query_result in query_results:
    #         for commit in query_result:
    #             for term_match in search_terms_in_commit(commit, terms):
    #                 console.print(term_match, style="red bold")


if __name__ == "__main__":
    main()
