-- SQL query to demonstrate RIGHT JOIN
-- This query identifies departments that have no employees.

-- Sample tables (you can create these in your SQL environment)
-- Table: employees
-- Columns: employee_id (INT, PRIMARY KEY), employee_name (VARCHAR), department_id (INT, FOREIGN KEY referencing departments.department_id)

-- Table: departments
-- Columns: department_id (INT, PRIMARY KEY), department_name (VARCHAR)

SELECT
    d.department_name,
    COUNT(e.employee_id) AS employee_count
FROM
    departments d
RIGHT JOIN
    employees e ON d.department_id = e.department_id
GROUP BY
    d.department_name
HAVING
    COUNT(e.employee_id) = 0;

-- Explanation:
-- 1. The RIGHT JOIN ensures that all departments are included in the result, even if they don't have any employees.
-- 2. The ON clause specifies the join condition: matching department_id in both tables.
-- 3. COUNT(e.employee_id) counts the number of employees in each department. If a department has no employees, this count will be 0.
-- 4. GROUP BY d.department_name groups the results by department name to allow for the count.
-- 5. HAVING COUNT(e.employee_id) = 0 filters the results to only show departments with no employees.