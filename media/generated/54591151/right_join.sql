-- Sample Data for employees table
CREATE TABLE employees (
    employee_id INT PRIMARY KEY,
    employee_name VARCHAR(255),
    department_id INT
);

-- Sample Data for departments table
CREATE TABLE departments (
    department_id INT PRIMARY KEY,
    department_name VARCHAR(255)
);

-- Insert sample data into employees table
INSERT INTO employees (employee_id, employee_name, department_id) VALUES
(1, 'John Doe', 1),
(2, 'Jane Smith', 2),
(3, 'Robert Jones', 1);

-- Insert sample data into departments table
INSERT INTO departments (department_id, department_name) VALUES
(1, 'Sales'),
(2, 'Marketing'),
(3, 'HR'),
(4, 'Finance');

-- SQL query demonstrating a right join
SELECT 
    e.employee_name,
    d.department_name,
    d.department_id
FROM 
    employees e
RIGHT JOIN 
    departments d ON e.department_id = d.department_id;

-- Clean up tables
DROP TABLE IF EXISTS employees;
DROP TABLE IF EXISTS departments;