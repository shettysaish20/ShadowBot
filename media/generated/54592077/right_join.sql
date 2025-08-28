-- SQL query to demonstrate a RIGHT JOIN

-- The RIGHT JOIN (or RIGHT OUTER JOIN) returns all rows from the right table (table_2 in this example),
-- even if there are no matching rows in the left table (table_1).
-- If there are no matching rows in the left table, the result will contain NULL values for the columns from the left table.

-- Let's assume we have two tables:
-- 'employees' (left table) with columns: employee_id, employee_name, department_id
-- 'departments' (right table) with columns: department_id, department_name

-- The following query will return all departments, and the corresponding employees in those departments.
-- If a department has no employees, the employee-related columns will be NULL.

SELECT
    employees.employee_id,
    employees.employee_name,
    departments.department_id,
    departments.department_name
FROM
    employees
RIGHT JOIN
    departments ON employees.department_id = departments.department_id;

-- Explanation:
-- 1. 'employees' is the left table, and 'departments' is the right table.
-- 2. The 'RIGHT JOIN' ensures that all rows from the 'departments' table are included in the result.
-- 3. The 'ON' clause specifies the join condition: 'employees.department_id = departments.department_id'.
-- 4. If an employee's department_id matches a department's department_id, the corresponding employee information is included in the result.
-- 5. If a department has no matching employee (i.e., no employee with the same department_id), the employee-related columns (employee_id, employee_name) will be NULL for that department.