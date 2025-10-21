"""
Create a sample PDF file for testing.
Uses PyMuPDF to generate a simple PDF with text content.
"""

import pymupdf


def create_sample_pdf(filename="sample.pdf"):
    """Create a simple PDF with educational content."""

    # Create a new PDF document
    doc = pymupdf.open()

    # Page 1: Introduction
    page1 = doc.new_page()
    text1 = """
    Calculus Study Guide

    Chapter 1: Introduction to Derivatives

    A derivative represents the rate of change of a function with respect to a variable.
    In calculus, the derivative of a function f(x) is denoted as f'(x) or df/dx.

    Key Concepts:
    - The derivative measures instantaneous rate of change
    - Geometrically, it represents the slope of the tangent line
    - Derivatives are fundamental to optimization problems

    The Power Rule:
    If f(x) = x^n, then f'(x) = n * x^(n-1)

    Example:
    f(x) = x³
    f'(x) = 3x²
    """

    page1.insert_text((50, 50), text1, fontsize=11)

    # Page 2: More content
    page2 = doc.new_page()
    text2 = """
    Chapter 2: Chain Rule

    The chain rule is used to differentiate composite functions.
    If y = f(g(x)), then dy/dx = f'(g(x)) * g'(x)

    Steps:
    1. Identify the outer function f and inner function g
    2. Find the derivative of the outer function f'(g(x))
    3. Find the derivative of the inner function g'(x)
    4. Multiply the results

    Example:
    Let y = (x² + 1)³
    Outer function: f(u) = u³, where u = x² + 1
    Inner function: g(x) = x² + 1

    f'(u) = 3u²
    g'(x) = 2x

    dy/dx = 3(x² + 1)² * 2x = 6x(x² + 1)²
    """

    page2.insert_text((50, 50), text2, fontsize=11)

    # Page 3: Practice problems
    page3 = doc.new_page()
    text3 = """
    Practice Problems

    1. Find the derivative of f(x) = 5x⁴ - 3x² + 7
       Solution: f'(x) = 20x³ - 6x

    2. Find the derivative of g(x) = (2x + 1)⁵
       Solution: Using chain rule, g'(x) = 5(2x + 1)⁴ * 2 = 10(2x + 1)⁴

    3. Find the derivative of h(x) = x² * sin(x)
       Solution: Using product rule, h'(x) = 2x*sin(x) + x²*cos(x)

    Tips for Success:
    - Practice regularly
    - Understand the concepts, don't just memorize
    - Draw graphs to visualize derivatives
    - Check your work by taking derivatives of simple functions
    """

    page3.insert_text((50, 50), text3, fontsize=11)

    # Save the PDF
    doc.save(filename)
    doc.close()

    print(f"✓ Created {filename} with 3 pages")
    print(f"  Page 1: Introduction to Derivatives")
    print(f"  Page 2: Chain Rule")
    print(f"  Page 3: Practice Problems")


if __name__ == "__main__":
    create_sample_pdf()
