classdef decomposeAngleVoltageSchurTest < matlab.unittest.TestCase
    %decomposeAngleVoltageSchurTest Unit tests for Schur decomposition.

    methods (TestClassSetup)
        function addSourceFolder(testCase)
            projectRoot = fileparts(fileparts(mfilename('fullpath')));
            testCase.applyFixture(matlab.unittest.fixtures.PathFixture( ...
                fullfile(projectRoot, 'src')));
        end
    end

    methods (Test, TestTags = {'Unit'})
        function testRealMatrixFactorization(testCase)
            matrix = [-1, -0.5; 0.2, 1];

            result = decomposeAngleVoltageSchur(matrix);

            testCase.verifyEqual(result.schurComplement, -0.9, AbsTol=1e-14);
            testCase.verifyEqual(result.characteristicDeterminant, -0.9, ...
                AbsTol=1e-14);
            testCase.verifyEqual(result.factorizationResidual, 0, AbsTol=1e-14);
        end

        function testComplexMatrixFactorization(testCase)
            matrix = [1 + 2i, 0.4 - 0.1i; -0.3i, 2 - 0.5i];

            result = decomposeAngleVoltageSchur(matrix);

            testCase.verifyEqual( ...
                result.voltageBlock * result.schurComplement, det(matrix), ...
                AbsTol=1e-13);
        end

        function testTransferFunctionFactorization(testCase)
            s = tf('s');
            matrix = [(s + 2)/(s + 1), 1/(s + 3); 0.2, (s + 4)/(s + 2)];

            result = decomposeAngleVoltageSchur(matrix);
            residualAtOneRadPerSecond = evalfr( ...
                result.factorizationResidual, 1i);

            testCase.verifyEqual(residualAtOneRadPerSecond, 0, AbsTol=1e-10);
        end

        function testAnglePivotFactorization(testCase)
            matrix = [2, -0.5; 0.2, 1];

            result = decomposeAngleVoltageSchur(matrix, Pivot="angle");

            testCase.verifyEqual( ...
                result.pivotBlock * result.schurComplement, det(matrix), ...
                AbsTol=1e-14);
        end

        function testInvalidSizeErrors(testCase)
            matrix = eye(3);

            testCase.verifyError( ...
                @() decomposeAngleVoltageSchur(matrix), ...
                'SchurAngleVoltage:InvalidSize');
        end

        function testSingularVoltagePivotErrors(testCase)
            matrix = [1, 2; 3, 0];

            testCase.verifyError( ...
                @() decomposeAngleVoltageSchur(matrix), ...
                'SchurAngleVoltage:SingularPivot');
        end
    end
end
