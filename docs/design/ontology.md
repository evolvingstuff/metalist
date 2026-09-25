# Personal Knowledge System - Tag Ontology Reference

Status: this document describes the long-term ontology design (including `#tag`).
Symmetric associations (`~`) were tried and dropped; they are not planned.

For the currently-implemented v1 rule DSL (plain tag tokens, `=>` and `=`, no negation), see:
- `docs/design/ontology-rules-v1.md`

## Core Operators

### Implication (`=>`)
- **Asymmetric** relationship
- Creates one-way logical connection
- Example: `#programming => #technology`

### Equality (`=`)
- **Syntactic sugar** for bidirectional implication
- `A = B` is equivalent to `A => B` and `B => A`
- Example: `#math = #mathematics`

## Data Types

### Tags
- Start with `#`
- No spaces allowed
- Example: `#machine-learning`, `#data_science`

### Text
- Must be surrounded by double quotes `" "`
- Can only appear on **left-hand side** of implications
- Can be **negated** with `-` prefix
- Examples: `"apple"`, `-"spam"`

### Regex
- Must be surrounded by forward slashes `/ /`
- Can only appear on **left-hand side** of implications  
- Can be **negated** with `-` prefix
- Examples: `/^\d{3}-\d{2}-\d{4}$/`, `-/cat|dog/`

## Important Constraints

### Text and Regex Limitations
- **Only on left-hand side** of implications
- **Can be negated** with `-` prefix

```
✅ Valid:   "apple" => #fruit
✅ Valid:   -"spam" => #not-spam
✅ Valid:   /\d+/ => #number
❌ Invalid: #fruit => "apple"
```

## Cartesian Product Expansion

Multiple terms on either side expand to all combinations:

```
#a #b => #c #d
```

Expands to:
- `#a => #c`
- `#a => #d`
- `#b => #c`
- `#b => #d`

This applies to both operators (`=>` and `=`).

## Contexts

### Syntax
- Surrounded by parentheses `( )`
- Only on **left-hand side** of implications
- Creates **AND condition** - all terms must be simultaneously present

### Examples
```
("apple" #diet) => #healthy
("apple" #tech) => #Apple-corp
```

### Multiple Contexts
Multiple contexts create Cartesian product:

```
("apple" #diet) ("fruit" #organic) => #healthy #nutritious
```

Expands to:
- `("apple" #diet) => #healthy`
- `("apple" #diet) => #nutritious`
- `("fruit" #organic) => #healthy`
- `("fruit" #organic) => #nutritious`

## Chaining

You can chain operators to create complex relationships:

```
/^\+?[ 1-9][0-9]{7,14}$/ => #phone-number => #contact-method
```

Creates both:
- `/^\+?[ 1-9][0-9]{7,14}$/ => #phone-number`
- `#phone-number => #contact-method`

### Complex Chain Example
```
#probability #statistics => #math = #mathematics => #logic
```

Equivalent to:
```
#probability => #math
#statistics => #math
#math => #mathematics
#mathematics => #math
#math => #logic
```

## Search Behavior

Implementation status: **partial**.

This document describes the planned ontology/implication search model.
The current implementation includes v1 ontology **implication + matcher** rules
and uses them to infer effective tags during search. See:
- Syntax: `docs/ui/search-syntax.md`
- Current semantics: `docs/ui/search-semantics.md`
- Rule language: `docs/design/ontology-rules-v1.md`

For the current UI-level query grammar and warnings (syntax-only, not semantics), see:
- `docs/ui/search-syntax.md`

### Direct Tag Search (`#tag`)
Returns:
- Content directly tagged with `#tag`
- Content that implies `#tag` (anything on LHS of `=> #tag`)

## Key Properties

- **Implications are asymmetric** (unless explicitly defined both ways)
- **Text/regex can only trigger implications, never be implied**
- **Contexts enable disambiguation through co-occurrence**
- **Chaining creates transitive relationships**
- **Search includes everything that logically implies the target**
