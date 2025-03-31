# Known Bugs

----

## Errors when moving notes

When moving notes up or down in the outline, it works fine 
for outermost layer (notes without parents),
but fails when moving child notes within parents.

1. Click into note A
2. Press shift-cmd-enter to create child A.A
3. Press cmd-enter to create sibling A.B
4. with A.B selected, press cmd-uparrow. This will cause server errors

----