import pytest

from filingqa.numfmt import contains_value, extract_numbers, filing_forms, numeric_match

APPLE_REVENUE = 391035000000


def test_millions_wording_matches_xbrl_raw_value():
    assert numeric_match("Net sales were $391,035 million.", APPLE_REVENUE)
    assert numeric_match("about $391.0 billion", APPLE_REVENUE)
    assert not numeric_match("391,035", APPLE_REVENUE)  # no implicit table-scale guessing
    assert numeric_match("391,035", 391035)
    assert numeric_match("391035000000", APPLE_REVENUE)


def test_near_miss_digit_errors_are_rejected():
    assert not numeric_match("$13,137 million", 13107e6)
    assert numeric_match("$13,107 million", 13107e6)


def test_tolerance_and_mismatch():
    assert numeric_match("$391,100 million", APPLE_REVENUE, tol=0.005)
    assert not numeric_match("$391,100 million", APPLE_REVENUE, tol=0.0001)
    assert not numeric_match("$93,736 million", APPLE_REVENUE)
    assert not numeric_match("not found in the filings", APPLE_REVENUE)


def test_years_are_not_mistaken_for_values():
    assert extract_numbers("fiscal year 2024") == []
    assert numeric_match("In fiscal 2024 it was $2,024 million", 2024e6)


def test_units_parse():
    assert extract_numbers("$1.5 trillion") == [1.5e12]
    assert extract_numbers("$12 billion and $3,400 thousand") == [12e9, 3.4e6]


def test_negative_in_parentheses_matches_signed_value():
    assert numeric_match("net loss of $(45) million", -45e6)


def test_filing_forms():
    forms = filing_forms(APPLE_REVENUE)
    assert forms[0] == "391,035"
    assert "391.0 billion" in forms
    assert "500" not in filing_forms(500e6)  # too ambiguous to search for bare


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Net sales | $391,035 | $383,285", True),
        ("Net sales | $1,391,035", False),  # glued to another digit group
        ("Net sales | $391,0355", False),
        ("Revenue was $391.0 billion this year", True),
        ("Revenue was 391,035.5", False),
        ("unrelated 12,345", False),
    ],
)
def test_contains_value(text, expected):
    assert contains_value(text, APPLE_REVENUE) is expected


@pytest.mark.parametrize("text", ["-$45 million", "$-45 million", "−$45 million",
                                  "$(45) million", "($45 million)", "(45 million)"])
def test_negative_notations_preserve_sign(text):
    assert extract_numbers(text) == [-45e6]
    assert numeric_match(text, -45e6)
    assert not numeric_match(text, 45e6)


@pytest.mark.parametrize("text", ["$45 million", "+$45 million", "$+45 million"])
def test_positive_amount_cannot_match_loss(text):
    assert numeric_match(text, 45e6)
    assert not numeric_match(text, -45e6)


@pytest.mark.parametrize("text", ["$391,035 million.", "$391,035 million, compared with last year",
                                  "$391.035 billion;", "$391035000000.", "$391,035 million!"])
def test_sentence_punctuation_is_not_a_malformed_number(text):
    assert numeric_match(text, APPLE_REVENUE)


@pytest.mark.parametrize("text", ["45%", "45 percent", "45 basis points", "EUR 45 million",
                                  "€45 million", "45 million euros", "1,23 million", "1.2.3",
                                  "--45 million", "$(45 million", "$45) million", "1e6",
                                  "AAPL-FY2024#0045", "[AAPL-FY2024#0045]"])
def test_non_usd_or_malformed_quantities_do_not_match(text):
    assert not numeric_match(text, 45e6)
    assert not numeric_match(text, 45)


def test_zero_multiple_quantities_and_explicit_small_dollars():
    assert numeric_match("FY2024: $0.00; FY2023: -$45 million", 0)
    assert numeric_match("FY2024: $0.00; FY2023: -$45 million", -45e6)
    assert not numeric_match("-$1 million", 0)
    assert numeric_match("$2,024", 2024)
    assert extract_numbers("45 and 46") == [45, 46]
    assert not numeric_match("45", 45e6)
    assert numeric_match("45 mm", 45e6)
    assert numeric_match("45 k", 45000)


def test_numeric_match_is_not_claim_entailment():
    # Deliberately numeric only: the reviewed evidence labels handle citation selection.
    assert numeric_match("Last year -$45 million; this year $10 million", -45e6)
    assert not numeric_match("net loss of $45 million", -45e6)


@pytest.mark.parametrize("value,tol", [(float("nan"), .001), (1, -1), (1, float("inf"))])
def test_invalid_target_or_tolerance_is_rejected(value, tol):
    with pytest.raises(ValueError):
        numeric_match("$1", value, tol)


def test_dates_and_malformed_citation_ids_do_not_supply_answer_values():
    assert extract_numbers("[JPM-FY2024#177556] on 2024-09-30") == []
    assert not numeric_match("[JPM-FY2024#177556]", 56)
    assert not numeric_match("2024-09-30", -30)
    assert numeric_match("$45 millions", 45e6)


@pytest.mark.parametrize("symbol", ["€", "£", "¥"])
@pytest.mark.parametrize("template", ["{} 45 million", "{} -45 million", "45 million {}",
                                     "45 {}", "(45 million) {}"])
def test_spaced_or_suffix_foreign_currency_is_not_usd(symbol, template):
    text = template.format(symbol)
    assert not numeric_match(text, 45e6)
    assert not numeric_match(text, -45e6)
    assert not numeric_match(text, 45)


@pytest.mark.parametrize("text,value", [("$ 45 million", 45e6), ("-$45 million", -45e6),
                                        ("USD 45 million", 45e6), ("45 million USD", 45e6),
                                        ("$(45) million", -45e6), ("(45 million)", -45e6),
                                        ("($45)", -45), ("(5,000)", -5000),
                                        ("USD (5)", -5), ("(5) dollars", -5)])
def test_explicit_usd_and_marked_accounting_controls(text, value):
    assert numeric_match(text, value)


@pytest.mark.parametrize("text", ["(5)", "note (5)", "(5.0)", "reference (45)"])
def test_bare_parenthesized_note_does_not_count_as_negative_amount(text):
    assert extract_numbers(text) == []


@pytest.mark.parametrize("text", [
    "€-45 million", "£-45 million", "¥−45 million", "EUR-45 million",
    "USD-45 million", "-USD45 million", "-USD 45 million", "−USD 45 million",
    "-US$45 million", "-US $45 million", "US$45 million", "C$45 million",
    "HK$45 million", "₹45 million", "₹-45 million", "(USD 45 million)",
])
def test_unsupported_currency_prefixes_never_restart_as_positive(text):
    assert extract_numbers(text) == []
    assert not numeric_match(text, 45e6)
    assert not numeric_match(text, -45e6)


@pytest.mark.parametrize("symbol", ["€", "£", "¥", "₹", "₩", "₽", "₺", "₪", "₱"])
@pytest.mark.parametrize("template", ["{}45 million", "{} -45 million", "{}-45 million",
                                     "{}(45 million)", "45 million{}", "45 million {}"])
def test_known_foreign_symbols_fail_closed_in_each_position(symbol, template):
    assert extract_numbers(template.format(symbol)) == []


@pytest.mark.parametrize("text,value", [("fraud $45 million", 45e6),
                                        ("entrepreneur $5 million", 5e6),
                                        ("compound $45 million", 45e6),
                                        ("impound $45 million", 45e6)])
def test_currency_codes_do_not_match_word_suffixes(text, value):
    assert numeric_match(text, value)


@pytest.mark.parametrize("prefix", ["€", "£", "¥", "₹", "EUR", "GBP", "CAD", "C$", "HK$", "A$"])
@pytest.mark.parametrize("sign", ["", "-", "−", "+", "–"])
@pytest.mark.parametrize("space_before,space_after", [("", ""), (" ", ""), ("", " "),
                                                     (" ", " "), ("\t", "\n")])
def test_complete_foreign_prefix_consumption(prefix, sign, space_before, space_after):
    text = f"{prefix}{space_before}{sign}{space_after}45 million"
    assert extract_numbers(text) == []
    assert not numeric_match(text, 45e6)
    assert not numeric_match(text, -45e6)


@pytest.mark.parametrize("text", ["€- 45 million", "EUR- 45 million", "USD- 45 million",
                                  "US$- 45 million", "loss- $45 million", "C$ 45 million",
                                  "HK$ 45 million", "A$ 45 million", "C$ -45 million",
                                  "-USD 45 million", "- US $45 million"])
def test_round_three_complete_token_regressions(text):
    assert extract_numbers(text) == []


@pytest.mark.parametrize("currency", ["€", "£", "¥", "₹", "EUR", "GBP", "CAD", "C$", "HK$"])
@pytest.mark.parametrize("separator", ["", " ", "\t"])
def test_complete_foreign_suffix_consumption(currency, separator):
    assert extract_numbers(f"45 million{separator}{currency}") == []


@pytest.mark.parametrize("dash", ["–", "‒", "－", "﹣", "—"])
@pytest.mark.parametrize("space", ["", " ", "\t"])
def test_typographic_sign_like_dash_is_rejected(dash, space):
    assert extract_numbers(f"{dash}{space}$45 million") == []
    assert extract_numbers(f"{dash}{space}45 million") == []


@pytest.mark.parametrize("text", ["$40 - $45 million", "$40-$45 million", "$40 -$45 million",
                                  "$40- $45 million", "$40 million−$45 million",
                                  "40–45 million", "-$40 million - -$45 million"])
def test_ambiguous_hyphen_range_or_binary_expression_has_no_loss_endpoint(text):
    assert extract_numbers(text) == []
    assert not numeric_match(text, -45e6)


@pytest.mark.parametrize("text", ["non-US $45 million", "ex-US $45 million",
                                  "non-US USD 45 million", "fraud $45 million"])
def test_ordinary_words_and_regional_adjectives_remain_prose(text):
    assert extract_numbers(text) == [45e6]


@pytest.mark.parametrize("separator", ["; ", " and ", ", "])
def test_independent_amounts_preserve_their_signs(separator):
    assert extract_numbers(f"$40 million{separator}-$45 million") == [40e6, -45e6]
    assert numeric_match(f"$40 million{separator}-$45 million", -45e6)


@pytest.mark.parametrize("sign", ["-", "−", "+"])
@pytest.mark.parametrize("before,after", [("", ""), (" ", ""), ("", " "), ("\t", "\n")])
def test_supported_sign_dollar_whitespace_controls(sign, before, after):
    expected = 45e6 if sign == "+" else -45e6
    assert extract_numbers(f"{sign}{before}${after}45 million") == ([] if before else [expected])
    assert extract_numbers(f"${before}{sign}{after}45 million") == ([] if after else [expected])


@pytest.mark.parametrize("code", ["USD", "US"])
@pytest.mark.parametrize("sign", ["-", "−", "+", "–"])
@pytest.mark.parametrize("space", ["", " ", "\t"])
def test_sign_before_currency_code_or_contiguous_after_code_fails_closed(code, sign, space):
    assert extract_numbers(f"{sign}{space}{code} $45 million") == []
    assert extract_numbers(f"{code}{sign}{space}45 million") == []


@pytest.mark.parametrize("text", ["45 millionEUR", "45 millionGBP", "45 millionCAD",
                                  "45 millionxyz", "45 billiontypo"])
def test_malformed_scale_word_does_not_fall_back_to_unscaled_amount(text):
    assert extract_numbers(text) == []


@pytest.mark.parametrize("currency", ["€", "EUR", "£", "CAD", "C$", "HK$"])
@pytest.mark.parametrize("sign", ["-", "−", "–"])
@pytest.mark.parametrize("space", ["", " "])
def test_foreign_suffix_sign_chain_is_consumed_before_usd_validation(currency, sign, space):
    assert extract_numbers(f"45 million {sign}{space}{currency}") == []


@pytest.mark.parametrize("text", ["45USD", "($45)USD", "45dollars"])
def test_unspaced_word_currency_suffix_is_unsupported(text):
    assert extract_numbers(text) == []


@pytest.mark.parametrize("text", ["- $45 million", "\n- $45 million", "Results:\n- $45 million",
                                  "FY2024 - $45 million", "Net income - $45 million",
                                  "# Header\n- $45 million", "$ - 45 million", "- 45 million",
                                  "− $45 million", "+ $45 million", "-\n$45 million"])
def test_spaced_sign_bullet_or_label_separator_is_ambiguous(text):
    assert extract_numbers(text) == []
    assert not numeric_match(text, -45e6)
    assert not numeric_match(text, 45e6)


@pytest.mark.parametrize("text", ["-$45 million", "$-45 million", "-45 million", "−$45 million",
                                  "USD -45 million", "$ -45 million", "-$ 45 million"])
def test_attached_sign_controls_survive_spaced_sign_rejection(text):
    assert extract_numbers(text) == [-45e6]


@pytest.mark.parametrize("annotation", ["(-5%)", "(−2.8% YoY)", "(-5 percent)",
                                        "(-5 basis points)", "(-5 bps)"])
def test_percent_change_is_not_a_usd_range_endpoint(annotation):
    assert extract_numbers(f"$45 million {annotation}") == [45e6]


@pytest.mark.parametrize("text", ["$1.2 billion ($1,200 million)",
                                  "$391.0 billion ($391,035 million)",
                                  "Net loss was $1.2 billion ($1,200 million)",
                                  "$1.2 billion USD ($1,200 million)"])
def test_immediate_parenthesized_restatement_is_not_a_loss(text):
    assert not numeric_match(text, -1.2e9)
    assert not numeric_match(text, -391035e6)


@pytest.mark.parametrize("separator", ["; ", " and "])
def test_independent_accounting_amount_keeps_negative_sign(separator):
    assert extract_numbers(f"$1.2 billion{separator}($45 million)") == [1.2e9, -45e6]


@pytest.mark.parametrize("text", ["a $45-million charge", "$45-million", "45-million",
                                  "$45 - million", "$45- million"])
def test_hyphenated_scale_compound_has_no_unscaled_fallback(text):
    assert extract_numbers(text) == []
    assert not numeric_match(text, 45)


@pytest.mark.parametrize("marker", ["‐", "‑", "‒", "–", "—", "﹘", "﹣", "－", "˗", "⁻", "₋", "➖", "±", "＋"])
@pytest.mark.parametrize("space", ["", " ", "\t"])
def test_unicode_sign_class_cannot_hide_a_negative_prefix(marker, space):
    assert extract_numbers(f"{marker}{space}$45 million") == []
    assert extract_numbers(f"{marker}{space}45 million") == []
    assert not numeric_match(f"{marker}{space}$45 million", 45e6)


@pytest.mark.parametrize("marker", ["₿", "؋", "₩", "₽", "₺", "₪", "₱", "＄", "﹩", "¤"])
@pytest.mark.parametrize("space", ["", " ", "\t"])
def test_unicode_currency_class_is_not_ascii_usd(marker, space):
    assert extract_numbers(f"-{marker}{space}45 million") == []
    assert extract_numbers(f"{marker}{space}-45 million") == []
    assert extract_numbers(f"$45 million {marker}") == []


@pytest.mark.parametrize("marker", ["\u200b", "\u2060", "\ufeff", "\u00ad", "\u200d",
                                    "\ufe0f", "\u0301", "\u0000"])
def test_controls_or_combining_marks_do_not_split_amount_prefix(marker):
    assert extract_numbers(f"-{marker}$45 million") == []
    assert extract_numbers(f"-{marker}45 million") == []
    assert extract_numbers(f"-$45{marker} million") == []
    assert extract_numbers(f"-$45 million{marker}") == []
    assert extract_numbers(f"-US{marker}D 45 million") == []


@pytest.mark.parametrize("opening,closing", [("（", "）"), ("﹙", "﹚"), ("❨", "❩"), ("⟮", "⟯")])
def test_noncanonical_parentheses_cannot_create_positive_inner_amount(opening, closing):
    assert extract_numbers(f"{opening}$45 million{closing}") == []
    assert extract_numbers(f"$45 million{closing}") == []


@pytest.mark.parametrize("marker", ["，", "．", "﹐", "﹒", "٫", "٬"])
def test_noncanonical_grouping_is_consumed_without_inner_value_fallback(marker):
    assert extract_numbers(f"$45{marker}000 million") == []
    assert extract_numbers(f"-$45 {marker} 000 million") == []


@pytest.mark.parametrize("marker", ["‐", "‑", "˗", "⁻", "₋", "➖"])
def test_unicode_sign_class_is_used_for_compounds_and_ranges(marker):
    assert extract_numbers(f"$45{marker}million") == []
    assert extract_numbers(f"$40{marker}$45 million") == []


@pytest.mark.parametrize("text,value", [("**-$45 million**", -45e6), (":$45 million", 45e6),
                                        ("**$45 million**", 45e6), (";−$45 million", -45e6)])
def test_benign_punctuation_does_not_blanket_reject_supported_amount(text, value):
    assert extract_numbers(text) == [value]


@pytest.mark.parametrize("group", ["[AAPL-FY2024#0123]", "[ AAPL-FY2024#0123 ]",
                                    "[AAPL-FY2024#0123, MSFT-FY2025#0012]",
                                    "[AAPL-FY2024#0123;MSFT-FY2025#0012]",
                                    "[JPM-FY2024#177556]"])
def test_canonical_citation_group_does_not_hide_accounting_restatement(group):
    text = f"$1.2 billion {group} ($1,200 million)"
    assert extract_numbers(text) == [1.2e9]
    assert not numeric_match(text, -1.2e9)


def test_canonical_citation_group_keeps_independent_accounting_amount():
    text = "$1.2 billion [AAPL-FY2024#0123]; ($45 million) [MSFT-FY2025#0012]"
    assert extract_numbers(text) == [1.2e9, -45e6]


@pytest.mark.parametrize("text", ["$４５ million", "$45 ｍｉｌｌｉｏｎ", "-ＵＳＤ 45 million"])
def test_fullwidth_numeric_or_marker_layout_has_no_ascii_fallback(text):
    assert extract_numbers(text) == []


@pytest.mark.parametrize("text", [r"-\$45 million", r"−\$45 million", "-**$45 million**",
                                  "-*$45 million*", "-`$45 million`", "(**$45 million**)",
                                  "- **$45 million**", r"- \$45 million", "-$**45 million**",
                                  "-$`45 million`", "€**$45 million**", "-\n**$45 million**"])
def test_punctuation_wrappers_cannot_hide_a_monetary_prefix(text):
    assert extract_numbers(text) == []
    assert not numeric_match(text, 45e6)
    assert not numeric_match(text, -45e6)


@pytest.mark.parametrize("wrapper", ["**", "*", "`", "\\"])
@pytest.mark.parametrize("marker", ["-", "−", "+", "(", "$", "€", "\u200b"])
@pytest.mark.parametrize("space", ["", " ", "\t"])
def test_hidden_prefix_punctuation_matrix(wrapper, marker, space):
    assert extract_numbers(f"{marker}{space}{wrapper}$45 million") == []


@pytest.mark.parametrize("text,value", [("**-$45 million**", -45e6), (":$45 million", 45e6),
                                        (";−$45 million", -45e6), ("**$45 million**", 45e6),
                                        ("Net income: **-$45 million**", -45e6),
                                        ("$10 million; **-$45 million**", -45e6)])
def test_benign_wrappers_before_intact_prefix_remain_valid(text, value):
    assert numeric_match(text, value)


@pytest.mark.parametrize("text", ["EUR **$45 million", "EUR**45 million", r"EUR\$45 million",
                                  "GBP *$45 million*", "CAD `$45 million`",
                                  "US\u200bD **$45 million", "ＥＵＲ **$45 million"])
def test_hidden_known_currency_word_is_checked_before_prose_boundary(text):
    assert extract_numbers(text) == []


@pytest.mark.parametrize("text,value", [("**USD -45 million**", -45e6),
                                        ("non-US **$45 million**", 45e6),
                                        ("fraud **$45 million**", 45e6)])
def test_intact_usd_prefix_and_ordinary_prose_wrapper_controls(text, value):
    assert numeric_match(text, value)


@pytest.mark.parametrize("text", ["**$1.2 billion** ($1,200 million)",
                                  "$1.2 billion **($1,200 million)**",
                                  "*$1.2 billion* ($1,200 million)",
                                  "**$1.2 billion** [AAPL-FY2024#0123] ($1,200 million)"])
def test_formatting_only_gaps_do_not_hide_accounting_restatement(text):
    assert extract_numbers(text) == [1.2e9]
    assert not numeric_match(text, -1.2e9)


@pytest.mark.parametrize("text", ["$40 million **-$45 million**", "$40 **-$45 million**",
                                  "$40 million `-$45 million`", "$40 million ~-$45 million~"])
def test_formatting_only_gap_does_not_hide_binary_range(text):
    assert extract_numbers(text) == []


@pytest.mark.parametrize("text,value", [("$10 million; **-$45 million**", -45e6),
                                        ("$10 million and **-$45 million**", -45e6),
                                        ("$1.2 billion; ($45 million)", -45e6)])
def test_formatting_adjacency_preserves_explicit_independent_amounts(text, value):
    assert numeric_match(text, value)


@pytest.mark.parametrize("text", ["**45 million** euros", "**$45 million** EUR",
                                  "45 million `EUR`", "**45 million**€", "$45 **million**",
                                  "**$45** million", "45 million _euros_",
                                  "**$45** _million_", "__$1.2 billion__ ($1,200 million)"])
def test_formatting_cannot_hide_suffix_currency_or_scale(text):
    assert extract_numbers(text) == []


@pytest.mark.parametrize("text", ["_EUR_ 45 million", "__EUR__ $45 million",
                                  "45 million _euros_", "-_ $45 million"])
def test_underscore_currency_classification_and_wrapper_scan(text):
    assert extract_numbers(text) == []


@pytest.mark.parametrize("text", ["-<b>$45 million</b>", "(<b>$45 million</b>)",
                                  "&minus;$45 million", "&#8722;$45 million",
                                  "&#x2212;$45 million", "-$45 million<br/>",
                                  "$10 million; -<b>$45 million</b>",
                                  "-<!-- hidden -->$45 million", "-<b $45 million"])
def test_html_like_messages_fail_closed_without_decoding(text):
    assert extract_numbers(text) == []


@pytest.mark.parametrize("text,value", [("AT&T: $45 million", 45e6),
                                        ("Revenue in the US: $45 million", 45e6),
                                        ("Revenue in USD: $45 million", 45e6),
                                        ("Revenue in dollars: $45 million", 45e6),
                                        ("**USD -45 million**", -45e6)])
def test_plain_usd_family_prose_continues_guard_without_false_rejection(text, value):
    assert numeric_match(text, value)


@pytest.mark.parametrize("text", ["-USD **$45 million", "US\u200bD **$45 million",
                                  "EUR **$45 million", "_USD_ **$45 million"])
def test_plain_usd_refinement_does_not_hide_earlier_or_decorated_markers(text):
    assert extract_numbers(text) == []


@pytest.mark.parametrize("code", ["C$", "HK$", "A$", "US$"])
@pytest.mark.parametrize("wrapper", ["**", "*", "`", "~", "_"])
@pytest.mark.parametrize("separator", ["", " ", "\t"])
def test_wrappers_cannot_hide_composite_dollar_suffix(code, wrapper, separator):
    assert extract_numbers(f"**$45 million**{separator}{wrapper}{code}{wrapper}") == []
    assert extract_numbers(f"$45 million {wrapper}{code}{wrapper}") == []


@pytest.mark.parametrize("text", [r"C\$45 million", r"-C\$45 million", "HK**$45 million**",
                                  "*C*$45 million", r"−HK\$45 million", r"45 million C\$",
                                  r"#\$45 million", r".\$45 million", r",\$45 million"])
def test_touching_formatting_cannot_bypass_attached_word_or_id_rule(text):
    assert extract_numbers(text) == []


@pytest.mark.parametrize("code", ["C", "HK", "A", "US"])
@pytest.mark.parametrize("wrapper", ["\\", "**", "*", "`", "~", "_"])
def test_touching_formatting_composite_dollar_is_rejected_in_each_position(code, wrapper):
    assert extract_numbers(f"{code}{wrapper}$45 million") == []
    assert extract_numbers(f"-{code}{wrapper}$45 million") == []
    assert extract_numbers(f"45 million {code}{wrapper}$") == []
    assert extract_numbers(f"**45 million** - {code}{wrapper}$") == []


@pytest.mark.parametrize("text,value", [(r"\$45 million", 45e6), (r"\-$45 million", -45e6),
                                        ("fraud **$45 million**", 45e6),
                                        ("Net income: **-$45 million**", -45e6),
                                        ("**USD -45 million**", -45e6)])
def test_touching_formatting_rule_preserves_benign_prefix_boundaries(text, value):
    assert numeric_match(text, value)


@pytest.mark.parametrize("text", ["**45 million** - EUR", "**45 million** -€",
                                  "**$45 million** - C$", "**45 million** - **EUR**",
                                  "**45 million** - _EUR_", r"**45 million** - C\$"])
def test_currency_sign_chain_continues_across_closing_wrappers(text):
    assert extract_numbers(text) == []


@pytest.mark.parametrize("text", ["&#8722$45 million", "&#8722 $45 million", "&#x2212$45 million",
                                  "&#X2212 $45 million", "&#40 45 million&#41"])
def test_numeric_entity_reference_is_rejected_without_semicolon(text):
    assert extract_numbers(text) == []


@pytest.mark.parametrize("marker", ["%", "percent", "percentage", "bps", "basis points",
                                    "hundred", "quadrillion", "bns", "tns", "mms"])
@pytest.mark.parametrize("wrapper", ["*", "**", "`", "~", "_", "\\"])
def test_existing_unit_markers_obscured_by_formatting_have_no_raw_usd_fallback(marker, wrapper):
    assert extract_numbers(f"{wrapper}$45{wrapper} {marker}") == []
    assert extract_numbers(f"$45 {wrapper}{marker}{wrapper}") == []
    assert extract_numbers(f"{wrapper}-$45{wrapper} {marker}") == []


@pytest.mark.parametrize("alias,value", [("bns", 45e9), ("tns", 45e12), ("mms", 45e6)])
def test_plain_existing_plural_aliases_keep_their_actual_scale(alias, value):
    assert extract_numbers(f"45 {alias}") == [value]
    assert extract_numbers(f"$45 {alias}") == [value]


@pytest.mark.parametrize("annotation", ["(-5 **percent**)", "(-5 **bps**)", "(-5 **basis points**)",
                                        "(-**5**%)", "(**-5** bps)"])
def test_obscured_percentage_annotation_is_not_a_usd_range_endpoint(annotation):
    assert extract_numbers(f"$45 million {annotation}") == [45e6]


@pytest.mark.parametrize("sign", ["-", "−", "+"])
@pytest.mark.parametrize("template", ["$45\\{sign}million", "**$45**{sign}million",
                                      "$45{sign}**million**", "$45 *{sign}* million",
                                      "$45{sign}_million_"])
def test_formatted_sign_scale_compound_has_no_raw_value_fallback(sign, template):
    text = template.format(sign=sign)
    assert extract_numbers(text) == []
    assert not numeric_match(text, 45)
    assert not numeric_match(text, -45)


@pytest.mark.parametrize("unit", ["million", "bns", "tns", "mms", "thousand", "milliontypo"])
def test_formatted_sign_scale_classification_uses_existing_aliases_and_scale_prefixes(unit):
    assert extract_numbers(f"$45\\-**{unit}**") == []


@pytest.mark.parametrize("text,expected", [
    ("$45 million (-5%)", [45e6]),
    ("$45 million **-5%**", [45e6]),
    ("$10 million; **-$45 million**", [10e6, -45e6]),
    ("$40 million **-$45 million**", []),
    (r"\$45 million", [45e6]),
])
def test_formatted_compound_check_does_not_treat_numeric_or_dollar_endpoints_as_units(text, expected):
    assert extract_numbers(text) == expected
