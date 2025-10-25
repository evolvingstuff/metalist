# Personal Knowledge System - Tag Ontology Reference

## Core Operators

### Implication (`=>`)
- **Asymmetric** relationship
- Creates one-way logical connection
- Example: `#programming => #technology`

### Association (`~`)
- **Symmetric** relationship
- Creates bidirectional loose connection
- Example: `#poker ~ #gambling` (implies `#gambling ~ #poker`)

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
- **Only in implications**, never associations
- **Only on left-hand side** of implications
- **Can be negated** with `-` prefix

```
✅ Valid:   "apple" => #fruit
✅ Valid:   -"spam" => #not-spam
✅ Valid:   /\d+/ => #number
❌ Invalid: #fruit ~ "apple"
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

This applies to all operators (`=>`, `~`, `=`).

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

## Association Inheritance

Associations propagate through implication chains:

```
#poker ~ #gambling
#gambling ~ #probability  
#probability => #math
```

Result: `#poker` is associated with `#math` through the chain.

## Association Distance Search

### Syntax
- `~#tag` - associations at distance 1 or less
- `~~#tag` - associations at distance 2 or less
- `~~~#tag` - associations at distance 3 or less

### Cumulative Nature
`~~#tag` includes:
- **Distance 0**: Direct matches to `#tag`
- **Distance 1**: Direct associations 
- **Distance 2**: Second-degree associations

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
"Las Vegas" => #Las_Vegas ~ #gambling ~ #probability #statistics => #math = #mathematics => #logic
```

Equivalent to:
```
"Las Vegas" => #Las_Vegas
#Las_Vegas ~ #gambling
#gambling ~ #probability
#gambling ~ #statistics
#probability => #math
#statistics => #math
#math => #mathematics
#mathematics => #math
#math => #logic
```

## Search Behavior

### Direct Tag Search (`#tag`)
Returns:
- Content directly tagged with `#tag`
- Content that implies `#tag` (anything on LHS of `=> #tag`)

### Association Search (`~#tag`, `~~#tag`, etc.)
Returns associations at specified distance or less.

**Note**: Associations are never included in direct tag searches - you must explicitly use the `~` operator.

## Key Properties

- **Implications are asymmetric** (unless explicitly defined both ways)
- **Associations are symmetric**
- **Text/regex can only trigger implications, never be implied**
- **Contexts enable disambiguation through co-occurrence**
- **Chaining creates transitive relationships**
- **Search includes everything that logically implies the target**