import { readFile } from "node:fs/promises";

const pairs = [
  {
    schemaPath: "report_generator/schemas/anomaly_report.schema.json",
    dataPath: "report_generator/examples/anomaly_report.example.json",
  },
  {
    schemaPath: "report_generator/schemas/daily_report.schema.json",
    dataPath: "report_generator/examples/daily_report.example.json",
  },
];

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function hasType(value, type) {
  if (type === "null") return value === null;
  if (type === "array") return Array.isArray(value);
  if (type === "object") return isObject(value);
  if (type === "integer") return Number.isInteger(value);
  if (type === "number") return typeof value === "number" && Number.isFinite(value);
  return typeof value === type;
}

function validateFormat(value, format) {
  if (typeof value !== "string") return true;
  if (format === "date") return /^\d{4}-\d{2}-\d{2}$/.test(value);
  if (format === "date-time") {
    return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value);
  }
  return true;
}

function validate(value, schema, path = "$") {
  const errors = [];

  if (schema.const !== undefined && value !== schema.const) {
    errors.push(`${path}: expected const ${JSON.stringify(schema.const)}`);
  }

  if (schema.enum && !schema.enum.includes(value)) {
    errors.push(`${path}: expected one of ${schema.enum.join(", ")}`);
  }

  if (schema.type) {
    const types = Array.isArray(schema.type) ? schema.type : [schema.type];
    if (!types.some((type) => hasType(value, type))) {
      errors.push(`${path}: expected type ${types.join(" or ")}`);
      return errors;
    }
  }

  if (typeof value === "string") {
    if (schema.minLength !== undefined && value.length < schema.minLength) {
      errors.push(`${path}: expected minLength ${schema.minLength}`);
    }
    if (schema.format && !validateFormat(value, schema.format)) {
      errors.push(`${path}: invalid ${schema.format} format`);
    }
  }

  if (typeof value === "number") {
    if (schema.minimum !== undefined && value < schema.minimum) {
      errors.push(`${path}: expected minimum ${schema.minimum}`);
    }
    if (schema.maximum !== undefined && value > schema.maximum) {
      errors.push(`${path}: expected maximum ${schema.maximum}`);
    }
  }

  if (Array.isArray(value)) {
    if (schema.minItems !== undefined && value.length < schema.minItems) {
      errors.push(`${path}: expected minItems ${schema.minItems}`);
    }
    if (schema.maxItems !== undefined && value.length > schema.maxItems) {
      errors.push(`${path}: expected maxItems ${schema.maxItems}`);
    }
    if (schema.items) {
      value.forEach((item, index) => {
        errors.push(...validate(item, schema.items, `${path}[${index}]`));
      });
    }
  }

  if (isObject(value)) {
    const properties = schema.properties ?? {};
    for (const key of schema.required ?? []) {
      if (!Object.prototype.hasOwnProperty.call(value, key)) {
        errors.push(`${path}: missing required property ${key}`);
      }
    }
    if (schema.additionalProperties === false) {
      for (const key of Object.keys(value)) {
        if (!Object.prototype.hasOwnProperty.call(properties, key)) {
          errors.push(`${path}: unexpected property ${key}`);
        }
      }
    }
    for (const [key, childSchema] of Object.entries(properties)) {
      if (Object.prototype.hasOwnProperty.call(value, key)) {
        errors.push(...validate(value[key], childSchema, `${path}.${key}`));
      }
    }
  }

  return errors;
}

async function main() {
  let hasErrors = false;
  for (const pair of pairs) {
    const schema = JSON.parse(await readFile(pair.schemaPath, "utf8"));
    const data = JSON.parse(await readFile(pair.dataPath, "utf8"));
    const errors = validate(data, schema);
    if (errors.length > 0) {
      hasErrors = true;
      console.log(`FAIL ${pair.dataPath}`);
      for (const error of errors) console.log(`- ${error}`);
    } else {
      console.log(`PASS ${pair.dataPath}`);
    }
  }
  if (hasErrors) process.exitCode = 1;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
