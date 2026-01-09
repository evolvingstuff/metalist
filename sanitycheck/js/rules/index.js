function suppressionRegex(ruleId) {
  return new RegExp(`lint: allow-${ruleId}\\s+rationale=".+"`);
}

function hasSuppression(context, node, ruleId) {
  const sourceCode = context.getSourceCode();
  const comments = sourceCode.getCommentsBefore(node);
  const regex = suppressionRegex(ruleId);

  let i = comments.length - 1;
  while (i >= 0) {
    const text = comments[i].value;
    if (regex.test(text)) {
      return true;
    }
    if (comments[i].loc.end.line < node.loc.start.line - 1) {
      return false;
    }
    i -= 1;
  }

  const onLine = sourceCode.getAllComments();
  let j = 0;
  while (j < onLine.length) {
    const c = onLine[j];
    if (c.loc.start.line === node.loc.start.line) {
      if (regex.test(c.value)) {
        return true;
      }
    }
    j += 1;
  }

  return false;
}

function calleeDottedName(callee) {
  if (callee.type === "Identifier") {
    return callee.name;
  }
  if (callee.type === "MemberExpression" && callee.computed === false) {
    const base = calleeDottedName(callee.object);
    if (base === null) {
      return null;
    }
    if (callee.property.type !== "Identifier") {
      return null;
    }
    return `${base}.${callee.property.name}`;
  }
  return null;
}

function tryHasAllowlistedCall(tryNode, allowedNames, allowedPrefixes) {
  const stack = [];
  let k = 0;
  while (k < tryNode.block.body.length) {
    stack.push(tryNode.block.body[k]);
    k += 1;
  }

  while (stack.length > 0) {
    const node = stack.pop();
    if (node && typeof node === "object") {
      if (node.type === "CallExpression") {
        const callee = calleeDottedName(node.callee);
        if (callee !== null) {
          let i = 0;
          while (i < allowedNames.length) {
            if (callee === allowedNames[i]) {
              return true;
            }
            i += 1;
          }
          let j = 0;
          while (j < allowedPrefixes.length) {
            if (callee.startsWith(allowedPrefixes[j])) {
              return true;
            }
            j += 1;
          }
        }
      }

      for (const key of Object.keys(node)) {
        if (key === "parent") {
          continue;
        }
        const value = node[key];
        if (Array.isArray(value)) {
          let t = 0;
          while (t < value.length) {
            if (value[t] && typeof value[t] === "object") {
              stack.push(value[t]);
            }
            t += 1;
          }
        } else if (value && typeof value === "object" && typeof value.type === "string") {
          stack.push(value);
        }
      }
    }
  }

  return false;
}

function containsThrow(blockStatement) {
  const stack = [blockStatement];
  while (stack.length > 0) {
    const node = stack.pop();
    if (node.type === "ThrowStatement") {
      return true;
    }
    for (const key of Object.keys(node)) {
      if (key === "parent") {
        continue;
      }
      const value = node[key];
      if (Array.isArray(value)) {
        let i = 0;
        while (i < value.length) {
          if (value[i] && typeof value[i] === "object") {
            stack.push(value[i]);
          }
          i += 1;
        }
      } else if (value && typeof value === "object" && typeof value.type === "string") {
        stack.push(value);
      }
    }
  }
  return false;
}

function containsReturn(blockStatement) {
  const stack = [blockStatement];
  while (stack.length > 0) {
    const node = stack.pop();
    if (node.type === "ReturnStatement") {
      return true;
    }
    for (const key of Object.keys(node)) {
      if (key === "parent") {
        continue;
      }
      const value = node[key];
      if (Array.isArray(value)) {
        let i = 0;
        while (i < value.length) {
          if (value[i] && typeof value[i] === "object") {
            stack.push(value[i]);
          }
          i += 1;
        }
      } else if (value && typeof value === "object" && typeof value.type === "string") {
        stack.push(value);
      }
    }
  }
  return false;
}

function isValueContext(node) {
  const parent = node.parent;
  if (!parent) {
    return false;
  }
  if (parent.type === "VariableDeclarator" && parent.init === node) {
    return true;
  }
  if (parent.type === "AssignmentExpression" && parent.right === node) {
    return true;
  }
  if (parent.type === "ReturnStatement" && parent.argument === node) {
    return true;
  }
  if (parent.type === "CallExpression") {
    let i = 0;
    while (i < parent.arguments.length) {
      if (parent.arguments[i] === node) {
        return true;
      }
      i += 1;
    }
  }
  return false;
}

const JS001 = {
  meta: {
    type: "problem",
    schema: [
      {
        type: "object",
        properties: {
          allowedTryCalleeNames: { type: "array", items: { type: "string" } },
          allowedTryCalleePrefixes: { type: "array", items: { type: "string" } }
        },
        additionalProperties: false
      }
    ],
    messages: {
      forbiddenTry: "try/catch is forbidden unless allowlisted",
      missingAllowlistedCall: "try block has no allowlisted external call",
      missingCatch: "try without catch is forbidden",
      catchMustThrow: "catch must throw (no silent handling)",
      catchMustNotReturn: "catch must not return"
    }
  },
  create(context) {
    const options = context.options[0];
    if (options === null || typeof options !== "object") {
      throw new Error("JS001 requires options");
    }
    const allowedNames = options.allowedTryCalleeNames;
    const allowedPrefixes = options.allowedTryCalleePrefixes;
    if (!Array.isArray(allowedNames)) {
      throw new Error("JS001 allowedTryCalleeNames must be an array");
    }
    if (!Array.isArray(allowedPrefixes)) {
      throw new Error("JS001 allowedTryCalleePrefixes must be an array");
    }

    return {
      TryStatement(node) {
        if (hasSuppression(context, node, "JS001")) {
          return;
        }

        if (node.handler === null) {
          context.report({ node, messageId: "missingCatch" });
          return;
        }

        if (!tryHasAllowlistedCall(node, allowedNames, allowedPrefixes)) {
          context.report({ node, messageId: "missingAllowlistedCall" });
        }

        if (containsReturn(node.handler.body)) {
          context.report({ node: node.handler, messageId: "catchMustNotReturn" });
        }
        if (!containsThrow(node.handler.body)) {
          context.report({ node: node.handler, messageId: "catchMustThrow" });
        }
      }
    };
  }
};

const JS002 = {
  meta: {
    type: "problem",
    schema: [],
    messages: {
      defaultParam: "default parameters are forbidden"
    }
  },
  create(context) {
    return {
      "FunctionDeclaration, FunctionExpression, ArrowFunctionExpression"(node) {
        if (hasSuppression(context, node, "JS002")) {
          return;
        }
        let i = 0;
        while (i < node.params.length) {
          if (node.params[i].type === "AssignmentPattern") {
            context.report({ node: node.params[i], messageId: "defaultParam" });
          }
          i += 1;
        }
      }
    };
  }
};

const JS003 = {
  meta: {
    type: "problem",
    schema: [],
    messages: {
      destructuringDefault: "destructuring defaults are forbidden"
    }
  },
  create(context) {
    function checkPattern(node) {
      const stack = [node];
      while (stack.length > 0) {
        const cur = stack.pop();
        if (cur && typeof cur === "object") {
          if (cur.type === "AssignmentPattern") {
            context.report({ node: cur, messageId: "destructuringDefault" });
          }
          for (const key of Object.keys(cur)) {
            if (key === "parent") {
              continue;
            }
            const value = cur[key];
            if (Array.isArray(value)) {
              let i = 0;
              while (i < value.length) {
                if (value[i] && typeof value[i] === "object") {
                  stack.push(value[i]);
                }
                i += 1;
              }
            } else if (value && typeof value === "object" && typeof value.type === "string") {
              stack.push(value);
            }
          }
        }
      }
    }

    return {
      ObjectPattern(node) {
        if (hasSuppression(context, node, "JS003")) {
          return;
        }
        checkPattern(node);
      },
      ArrayPattern(node) {
        if (hasSuppression(context, node, "JS003")) {
          return;
        }
        checkPattern(node);
      }
    };
  }
};

const JS004 = {
  meta: {
    type: "problem",
    schema: [],
    messages: {
      defaultingOperator: "defaulting operator is forbidden"
    }
  },
  create(context) {
    return {
      LogicalExpression(node) {
        if (hasSuppression(context, node, "JS004")) {
          return;
        }
        if (node.operator === "||" || node.operator === "??") {
          if (isValueContext(node)) {
            context.report({ node, messageId: "defaultingOperator" });
          }
        }
      },
      AssignmentExpression(node) {
        if (hasSuppression(context, node, "JS004")) {
          return;
        }
        if (node.operator === "||=" || node.operator === "??=") {
          context.report({ node, messageId: "defaultingOperator" });
        }
      }
    };
  }
};

export default {
  rules: {
    JS001,
    JS002,
    JS003,
    JS004
  }
};
