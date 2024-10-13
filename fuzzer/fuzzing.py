import subprocess
import random
import string
from pathlib import Path
import requests
from bs4 import BeautifulSoup, Tag, NavigableString
import json
from lxml import etree
import jpype
import jpype.imports
import astor
import ast
import os
import sys
import pkg_resources
import time
import tracemalloc
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_java_installation():
    try:
        result = subprocess.run(['java', '-version'], capture_output=True, text=True)
        logger.info(f"Java version:\n{result.stderr}")
        return True
    except FileNotFoundError:
        logger.error("Java is not found in system PATH.")
        return False

def check_jpype_version():
    jpype_version = pkg_resources.get_distribution("JPype1").version
    logger.info(f"JPype version: {jpype_version}")
    if pkg_resources.parse_version(jpype_version) < pkg_resources.parse_version("1.3.0"):
        logger.warning("Your JPype version might be outdated. Consider upgrading to the latest version.")
    return jpype_version

def check_local_repo():
    repo_path = os.path.join(os.getcwd())
    if not os.path.exists(repo_path):
        logger.error(f"Local repository not found at {repo_path}")
        sys.exit(1)
    logger.info(f"Local repository found at {repo_path}")

def generate_random_html():
    tags = ['div', 'p', 'span', 'a', 'h1', 'h2', 'h3', 'ul', 'li', 'table', 'tr', 'td']
    html = "<!DOCTYPE html><html><head><title>Fuzz Test</title></head><body>"
    for _ in range(random.randint(5, 30)):
        tag = random.choice(tags)
        content = ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(5, 50)))
        attributes = ' '.join([f'{attr}="{value}"' for attr, value in 
                               [('class', 'test-class'), ('id', f'id-{random.randint(1,100)}')]
                               if random.choice([True, False])])
        html += f"<{tag} {attributes}>{content}</{tag}>"
    html += "</body></html>"
    return html

def mutate_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    mutation_type = random.choice(['add', 'remove', 'modify', 'nest', 'attribute'])
    
    if mutation_type == 'add':
        new_tag = soup.new_tag(random.choice(['div', 'p', 'span']))
        new_tag.string = ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(5, 20)))
        random_tag = random.choice(list(soup.find_all()))
        random_tag.append(new_tag)
    elif mutation_type == 'remove':
        tags = list(soup.find_all())
        if tags:
            random_tag = random.choice(tags)
            random_tag.extract()
    elif mutation_type == 'modify':
        tags = list(soup.find_all())
        if tags:
            random_tag = random.choice(tags)
            random_tag.string = ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(5, 20)))
    elif mutation_type == 'nest':
        tags = list(soup.find_all())
        if len(tags) > 1:
            parent = random.choice(tags)
            child = random.choice(tags)
            if child != parent:
                child.extract()
                parent.append(child)
    else:  # attribute
        tags = list(soup.find_all())
        if tags:
            random_tag = random.choice(tags)
            attr_name = random.choice(['class', 'id', 'style', 'data-test'])
            attr_value = ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(5, 15)))
            random_tag[attr_name] = attr_value
    
    return str(soup)

def grammar_based_fuzzing():
    grammar = {
        "START": ["<html><head><title>{TITLE}</title></head><body>{BODY}</body></html>"],
        "TITLE": ["{WORD}", "{WORD} {WORD}", "{WORD} {WORD} {WORD}"],
        "BODY": ["{ELEMENT}", "{ELEMENT}{ELEMENT}", "{ELEMENT}{ELEMENT}{ELEMENT}"],
        "ELEMENT": ["<div>{CONTENT}</div>", "<p>{CONTENT}</p>", "<span>{CONTENT}</span>"],
        "CONTENT": ["{WORD}", "{WORD} {WORD}", "{ELEMENT}"],
        "WORD": ["".join(random.choices(string.ascii_lowercase, k=random.randint(3, 10))) for _ in range(10)]
    }

    def expand(symbol):
        while '{' in symbol and '}' in symbol:
            start = symbol.find('{')
            end = symbol.find('}', start)
            key = symbol[start+1:end]
            replacement = random.choice(grammar[key])
            symbol = symbol[:start] + replacement + symbol[end+1:]
        return symbol

    return expand("{START}")

def setup_jsoup():
    jsoup_jar = os.path.join(os.getcwd(), "lib", "jsoup-1.18.1.jar")
    if not os.path.exists(jsoup_jar):
        logger.error(f"Error: {jsoup_jar} not found.")
        logger.error("Please ensure the jsoup JAR file is in the correct directory.")
        sys.exit(1)
    
    if not jpype.isJVMStarted():
        jpype.startJVM(jpype.getDefaultJVMPath(), f"-Djava.class.path={jsoup_jar}", "-ea", "-Xmx256m")
    
    try:
        jpype.addClassPath(jsoup_jar)
        Jsoup = jpype.JClass("org.jsoup.Jsoup")
        return Jsoup
    except jpype.JException as e:
        logger.error(f"Error loading Jsoup class: {e}")
        logger.error(f"Classpath: {jsoup_jar}")
        logger.error("Available classes:")
        for cls in jpype.java.lang.ClassLoader.getSystemClassLoader().getDefinedPackages():
            logger.error(cls.getName())
        raise

def fuzz_test(iterations):
    bugs_found = []
    try:
        Jsoup = setup_jsoup()
    except Exception as e:
        logger.error(f"Error setting up Jsoup: {e}")
        return bugs_found

    for i in range(iterations):
        if i % 3 == 0:
            html = generate_random_html()
        elif i % 3 == 1:
            html = grammar_based_fuzzing()
        else:
            html = mutate_html(generate_random_html())
        
        try:
            # Start performance tracking
            start_time = time.time()
            # tracemalloc.start()

            # Parsing using Jsoup
            doc = Jsoup.parse(html)
            parsed_html = doc.html()
            parsed_html = str(parsed_html)  # Convert Java String to Python string

            # Stop performance tracking
            # _, peak = tracemalloc.get_traced_memory()
            # tracemalloc.stop()
            elapsed_time = time.time() - start_time

            # Check performance metrics
            if elapsed_time > 1.0:  # Arbitrary threshold for slow parsing
                bugs_found.append(f"Iteration {i}: Slow parsing - {elapsed_time:.2f}s")
            # if peak > 1024 * 1024:  # Arbitrary threshold for memory usage (1MB)
            #     bugs_found.append(f"Iteration {i}: High memory usage - {peak / 1024:.2f}KB")

            # Check for correct structure
            try:
                parser = etree.HTMLParser()
                etree.fromstring(parsed_html, parser)
            except etree.ParserError as e:
                bugs_found.append(f"Iteration {i}: Invalid HTML structure - {str(e)}")

        except Exception as e:
            bugs_found.append(f"Iteration {i}: Exception - {str(e)}")
        
        if i % 100 == 0:
            logger.info(f"Completed {i} iterations")
    
    return bugs_found

def improve_parser_analyzer(parsed_html):
    class HTMLAnalyzer(ast.NodeVisitor):
        def __init__(self):
            self.issues = []

        def visit_Call(self, node):
            if isinstance(node.func, ast.Attribute):
                if node.func.attr in ['getElementById', 'getElementsByClassName', 'getElementsByTagName']:
                    self.issues.append(f"Potential performance issue: using {node.func.attr}")
            self.generic_visit(node)

    try:
        tree = ast.parse(parsed_html)
        analyzer = HTMLAnalyzer()
        analyzer.visit(tree)
        return analyzer.issues
    except SyntaxError:
        return ["Syntax error in parsed HTML code supplied to analyzer"]

def write_report(bugs, parser_issues):
    report = "Fuzz Testing Report\n"
    report += "===================\n\n"
    
    if bugs:
        report += "Bugs found:\n"
        for bug in bugs:
            report += f"- {bug}\n"
    else:
        report += "No bugs found during fuzzing.\n"
    
    if parser_issues:
        report += "\nPotential parser issues:\n"
        for issue in parser_issues:
            report += f"- {issue}\n"
    
    logger.info(report)
    
    with open('fuzz_report.txt', 'w') as f:
        f.write(report)

def main():
    if not check_java_installation():
        logger.error("Please install Java and make sure it's in your system PATH.")
        return

    jpype_version = check_jpype_version()
    check_local_repo()

    try:
        bugs = fuzz_test(iterations=1000)

        sample_parser_code = """
            def parse_html(html):
                doc = BeautifulSoup(html, 'html.parser')
                elements = doc.getElementsByTagName('div')
                return elements
            """
        parser_issues = improve_parser_analyzer(sample_parser_code)
        
        write_report(bugs, parser_issues)
        logger.info("Fuzzing complete. Check fuzz_report.txt for results.")
    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        if jpype.isJVMStarted():
            jpype.shutdownJVM()

if __name__ == "__main__":
    main()
