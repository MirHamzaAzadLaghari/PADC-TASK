"""Unit tests for the calculation engine. Run: python -m unittest -v"""
import math
import unittest

from calculator.engine import CalcError, Calculator, format_number


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.c = Calculator()

    def check(self, expr, expected):
        self.assertEqual(self.c.calculate(expr), expected, expr)

    def fails(self, expr, message=None):
        with self.assertRaises(CalcError) as ctx:
            self.c.calculate(expr)
        if message:
            self.assertIn(message, str(ctx.exception))

    # --- arithmetic & precedence -------------------------------------------
    def test_basic_arithmetic(self):
        for expr, out in [("2+3", "5"), ("10-4", "6"), ("6*7", "42"), ("10/4", "2.5"), ("7/2", "3.5")]:
            self.check(expr, out)

    def test_precedence_and_parentheses(self):
        self.check("2+3*4", "14")
        self.check("(2+3)*4", "20")
        self.check("2*(3+4)*5", "70")
        self.check("100/10/5", "2")
        self.check("10-3-2", "5")

    def test_power_is_right_associative_and_unary_minus_binds_loosely(self):
        self.check("2^3^2", "512")
        self.check("-2^2", "-4")
        self.check("2^-2", "0.25")
        self.check("(-2)^2", "4")

    def test_unicode_operators(self):
        self.check("6×7", "42")
        self.check("84÷2", "42")
        self.check("10−3", "7")
        self.check("√81", "9")

    def test_implicit_multiplication(self):
        self.check("2(3+4)", "14")
        self.check("(1+2)(3+4)", "21")
        self.check("2pi", format_number(2 * math.pi))
        self.check("3sin(30)", "1.5")

    def test_float_noise_is_hidden(self):
        self.check("0.1+0.2", "0.3")
        self.check("0.3-0.1", "0.2")
        self.check("1/3", "0.333333333333")

    def test_big_integers_stay_exact_until_formatting(self):
        self.check("2^10", "1024")
        self.check("999999999999999+1", "1e+15")
        self.check("2^100", "1.26765060023e+30")

    # --- percent -----------------------------------------------------------
    def test_percent(self):
        self.check("50%", "0.5")
        self.check("200+10%", "220")
        self.check("200-10%", "180")
        self.check("200*10%", "20")

    # --- functions ---------------------------------------------------------
    def test_trig_degrees_exact_values(self):
        self.check("sin(0)", "0")
        self.check("sin(30)", "0.5")
        self.check("sin(90)", "1")
        self.check("sin(180)", "0")
        self.check("cos(60)", "0.5")
        self.check("cos(90)", "0")
        self.check("tan(45)", "1")
        self.check("sin(-90)", "-1")
        self.check("sin(450)", "1")

    def test_trig_radians(self):
        self.c.angle_mode = "RAD"
        self.check("sin(pi)", "0")
        self.check("cos(pi)", "-1")
        self.check("sin(pi/2)", "1")

    def test_inverse_trig(self):
        self.check("asin(1)", "90")
        self.check("acos(0)", "90")
        self.check("atan(1)", "45")

    def test_logs_and_roots(self):
        self.check("log(1000)", "3")
        self.check("log(8,2)", "3")
        self.check("log2(1024)", "10")
        self.check("ln(e)", "1")
        self.check("sqrt(144)", "12")
        self.check("cbrt(27)", "3")
        self.check("cbrt(-8)", "-2")
        self.check("root(81,4)", "3")
        self.check("exp(0)", "1")

    def test_misc_functions(self):
        self.check("abs(-5)", "5")
        self.check("5!", "120")
        self.check("0!", "1")
        self.check("20!", "2.43290200818e+18")
        self.check("mod(10,3)", "1")
        self.check("floor(2.7)", "2")
        self.check("ceil(2.1)", "3")
        self.check("round(2.567,2)", "2.57")

    def test_ans_constant(self):
        self.check("6*7", "42")
        self.check("ans+8", "50")

    # --- errors ------------------------------------------------------------
    def test_error_messages(self):
        self.fails("1/0", "divide by zero")
        self.fails("0^-1", "divide by zero")
        self.fails("sqrt(-1)", "Invalid")
        self.fails("ln(0)", "Invalid")
        self.fails("log(-5)", "Invalid")
        self.fails("tan(90)", "undefined")
        self.fails("asin(2)", "Invalid")
        self.fails("(-8)^0.5", "Invalid")
        self.fails("3.5!", "whole number")
        self.fails("(-3)!", "whole number")
        self.check("-3!", "-6")  # unary minus applies after the factorial
        self.fails("2000!", "too large")
        self.fails("9^9^9", "too large")
        self.fails("1e308*10", "too large")

    def test_syntax_errors(self):
        for bad in ["", "   ", "2+", "*3", "abc", "3 4", "2$3", "sin()", "sin(1,2)", "(2+3))", "5%%%x"]:
            self.fails(bad)

    def test_incomplete_input_is_auto_closed(self):
        self.check("(2+3", "5")
        self.check("sin(30", "0.5")
        self.check("2*(3+(4", "14")

    def test_expression_length_limit(self):
        self.fails("1+" * 400 + "1", "too long")

    def test_deep_nesting_does_not_crash(self):
        self.fails("(" * 450 + "1" + ")" * 450)

    # --- memory ------------------------------------------------------------
    def test_memory_register(self):
        self.c.memory_add(5)
        self.c.memory_add(7)
        self.c.memory_subtract(2)
        self.assertEqual(self.c.memory, 10)
        self.c.memory_clear()
        self.assertEqual(self.c.memory, 0)


class FormatTests(unittest.TestCase):
    def test_format_number(self):
        self.assertEqual(format_number(5.0), "5")
        self.assertEqual(format_number(-0.0), "0")
        self.assertEqual(format_number(0.1 + 0.2), "0.3")
        self.assertEqual(format_number(1e-7), "1e-7")
        self.assertEqual(format_number(10**20), "1e+20")
        self.assertEqual(format_number(123456789012345), "123456789012345")


if __name__ == "__main__":
    unittest.main()
