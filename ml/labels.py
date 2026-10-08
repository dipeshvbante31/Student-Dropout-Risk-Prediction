"""Single source of truth for feature metadata (labels, groups, coded-value names).

Coded-value names follow the UCI data dictionary. Where a code list is very long
(qualifications, occupations, nationality) the UI shows the raw code.
"""

# name -> (label, group, help)
FEATURE_META = {
    "marital_status": ("Marital status", "Demographics", "Marital status at enrollment."),
    "gender": ("Gender", "Demographics", "Recorded gender (dataset coding: 1 = male, 0 = female)."),
    "age_at_enrollment": ("Age at enrollment", "Demographics", "Age in years at enrollment."),
    "nationality": ("Nationality (code)", "Demographics", "Nationality code from the UCI data dictionary."),
    "international": ("International student", "Demographics", "Whether the student is international."),
    "displaced": ("Displaced from home", "Demographics", "Whether the student is displaced."),
    "educational_special_needs": ("Educational special needs", "Demographics", "Whether the student has recorded special educational needs."),
    "application_mode": ("Application mode", "Application and prior education", "Route through which the student applied."),
    "application_order": ("Application order", "Application and prior education", "Choice order of the course (0 = first choice, 9 = last)."),
    "course": ("Course", "Application and prior education", "Degree programme."),
    "daytime_evening_attendance": ("Attendance regime", "Application and prior education", "Daytime or evening classes."),
    "previous_qualification": ("Previous qualification (code)", "Application and prior education", "Qualification code from the UCI data dictionary."),
    "previous_qualification_grade": ("Previous qualification grade", "Application and prior education", "Grade of previous qualification (0-200)."),
    "admission_grade": ("Admission grade", "Application and prior education", "Admission grade (0-200)."),
    "mothers_qualification": ("Mother's qualification (code)", "Family background", "Qualification code from the UCI data dictionary."),
    "fathers_qualification": ("Father's qualification (code)", "Family background", "Qualification code from the UCI data dictionary."),
    "mothers_occupation": ("Mother's occupation (code)", "Family background", "Occupation code from the UCI data dictionary."),
    "fathers_occupation": ("Father's occupation (code)", "Family background", "Occupation code from the UCI data dictionary."),
    "debtor": ("Debtor", "Financial", "Whether the student is a debtor."),
    "tuition_fees_up_to_date": ("Tuition fees up to date", "Financial", "Whether tuition fees are paid up to date."),
    "scholarship_holder": ("Scholarship holder", "Financial", "Whether the student holds a scholarship."),
    "curricular_units_1st_sem_credited": ("Units credited", "First semester", "Curricular units credited in 1st semester."),
    "curricular_units_1st_sem_enrolled": ("Units enrolled", "First semester", "Curricular units enrolled in 1st semester."),
    "curricular_units_1st_sem_evaluations": ("Evaluations taken", "First semester", "Number of evaluations in 1st semester."),
    "curricular_units_1st_sem_approved": ("Units approved", "First semester", "Curricular units approved in 1st semester."),
    "curricular_units_1st_sem_grade": ("Average grade", "First semester", "Average grade in 1st semester (0-20)."),
    "curricular_units_1st_sem_without_evaluations": ("Units without evaluations", "First semester", "Units without evaluation in 1st semester."),
    "curricular_units_2nd_sem_credited": ("Units credited", "Second semester", "Curricular units credited in 2nd semester."),
    "curricular_units_2nd_sem_enrolled": ("Units enrolled", "Second semester", "Curricular units enrolled in 2nd semester."),
    "curricular_units_2nd_sem_evaluations": ("Evaluations taken", "Second semester", "Number of evaluations in 2nd semester."),
    "curricular_units_2nd_sem_approved": ("Units approved", "Second semester", "Curricular units approved in 2nd semester."),
    "curricular_units_2nd_sem_grade": ("Average grade", "Second semester", "Average grade in 2nd semester (0-20)."),
    "curricular_units_2nd_sem_without_evaluations": ("Units without evaluations", "Second semester", "Units without evaluation in 2nd semester."),
    "unemployment_rate": ("Unemployment rate (%)", "Economic context", "National unemployment rate at enrollment."),
    "inflation_rate": ("Inflation rate (%)", "Economic context", "National inflation rate at enrollment."),
    "gdp": ("GDP change (%)", "Economic context", "GDP change at enrollment."),
}
GROUP_ORDER = ["Demographics", "Application and prior education", "Family background",
               "Financial", "First semester", "Second semester", "Economic context"]

CATEGORICAL = ["marital_status", "application_mode", "course", "previous_qualification", "nationality",
               "mothers_qualification", "fathers_qualification", "mothers_occupation", "fathers_occupation"]
BINARY = ["gender", "daytime_evening_attendance", "displaced", "educational_special_needs", "debtor",
          "tuition_fees_up_to_date", "scholarship_holder", "international"]
FLOAT = ["previous_qualification_grade", "admission_grade", "curricular_units_1st_sem_grade",
         "curricular_units_2nd_sem_grade", "unemployment_rate", "inflation_rate", "gdp"]
# everything else is an integer count / code

VALUE_LABELS = {
    "marital_status": {1: "Single", 2: "Married", 3: "Widower", 4: "Divorced", 5: "Facto union", 6: "Legally separated"},
    "gender": {1: "Male", 0: "Female"},
    "daytime_evening_attendance": {1: "Daytime", 0: "Evening"},
    "application_mode": {1: "1st phase - general contingent", 2: "Ordinance 612/93", 5: "1st phase - special contingent (Azores)",
        7: "Holders of other higher courses", 10: "Ordinance 854-B/99", 15: "International student (bachelor)",
        16: "1st phase - special contingent (Madeira)", 17: "2nd phase - general contingent", 18: "3rd phase - general contingent",
        26: "Ordinance 533-A/99, item b2", 27: "Ordinance 533-A/99, item b3", 39: "Over 23 years old", 42: "Transfer",
        43: "Change of course", 44: "Technological specialization diploma holders", 51: "Change of institution/course",
        53: "Short cycle diploma holders", 57: "Change of institution/course (international)"},
    "course": {33: "Biofuel Production Technologies", 171: "Animation and Multimedia Design", 8014: "Social Service (evening)",
        9003: "Agronomy", 9070: "Communication Design", 9085: "Veterinary Nursing", 9119: "Informatics Engineering",
        9130: "Equinculture", 9147: "Management", 9238: "Social Service", 9254: "Tourism", 9500: "Nursing",
        9556: "Oral Hygiene", 9670: "Advertising and Marketing Management", 9773: "Journalism and Communication",
        9853: "Basic Education", 9991: "Management (evening)"},
}
YES_NO = {1: "Yes", 0: "No"}
for _k in ("displaced", "educational_special_needs", "debtor", "tuition_fees_up_to_date", "scholarship_holder", "international"):
    VALUE_LABELS[_k] = YES_NO

# Hard validity bounds: values outside are rejected (not merely "unusual").
HARD_BOUNDS = {
    "age_at_enrollment": (14, 100), "application_order": (0, 9),
    "previous_qualification_grade": (0, 200), "admission_grade": (0, 200),
    "curricular_units_1st_sem_grade": (0, 20), "curricular_units_2nd_sem_grade": (0, 20),
    "unemployment_rate": (0, 100), "inflation_rate": (-20, 100), "gdp": (-30, 30),
}
for _s in ("1st", "2nd"):
    for _u in ("credited", "enrolled", "evaluations", "approved", "without_evaluations"):
        HARD_BOUNDS[f"curricular_units_{_s}_sem_{_u}"] = (0, 100)

COURSE_NAMES = VALUE_LABELS["course"]
