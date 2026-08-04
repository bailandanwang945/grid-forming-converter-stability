classdef buildPowerPolarLinearizationTest < matlab.unittest.TestCase
    %BUILDPOWERPOLARLINEARIZATIONTEST Work-point transformation tests.

    methods (TestClassSetup)
        function addSourceFolder(testCase)
            projectRoot = fileparts(fileparts(mfilename('fullpath')));
            testCase.applyFixture(matlab.unittest.fixtures.PathFixture( ...
                fullfile(projectRoot, 'src')));
        end
    end

    methods (Test, TestTags = {'Unit'})
        function testInverseMatricesAtNonunitOperatingPoint(testCase)
            operatingPoint = struct('vd', 0.8, 'vq', 0.3, ...
                'id', 0.4, 'iq', -0.2);

            result = buildPowerPolarLinearization(operatingPoint);

            testCase.verifyEqual(result.Finverse*result.F, eye(2), ...
                AbsTol=1e-14);
            testCase.verifyLessThan(result.inverseResidual, 1e-14);
        end

        function testPolarToDqJacobianByFiniteDifference(testCase)
            operatingPoint = struct('vd', 0.8, 'vq', 0.3, ...
                'id', 0.4, 'iq', -0.2);
            result = buildPowerPolarLinearization(operatingPoint);
            h = 1e-6;
            phi = result.voltageAngle;
            magnitude = result.voltageMagnitude;
            fromPolar = @(angle, radius) ...
                radius*[cos(angle); sin(angle)];
            finiteDifference = [ ...
                (fromPolar(phi+h, magnitude)- ...
                    fromPolar(phi-h, magnitude))/(2*h), ...
                (fromPolar(phi, magnitude+h)- ...
                    fromPolar(phi, magnitude-h))/(2*h)];

            testCase.verifyEqual(result.F, finiteDifference, AbsTol=1e-9);
        end

        function testDqToPolarJacobianByFiniteDifference(testCase)
            operatingPoint = struct('vd', 0.8, 'vq', 0.3, ...
                'id', 0.4, 'iq', -0.2);
            result = buildPowerPolarLinearization(operatingPoint);
            h = 1e-6;
            voltage = [operatingPoint.vd; operatingPoint.vq];
            e1 = [1; 0];
            e2 = [0; 1];
            toPolar = @(value) [atan2(value(2), value(1)); norm(value)];
            finiteDifference = [ ...
                (toPolar(voltage+h*e1)-toPolar(voltage-h*e1))/(2*h), ...
                (toPolar(voltage+h*e2)-toPolar(voltage-h*e2))/(2*h)];

            testCase.verifyEqual( ...
                result.Finverse, finiteDifference, AbsTol=1e-9);
        end

        function testPowerCurrentJacobianByFiniteDifference(testCase)
            operatingPoint = struct('vd', 0.8, 'vq', 0.3, ...
                'id', 0.4, 'iq', -0.2);
            result = buildPowerPolarLinearization(operatingPoint);
            h = 1e-6;
            voltage = [operatingPoint.vd; operatingPoint.vq];
            current = [operatingPoint.id; operatingPoint.iq];
            e1 = [1; 0];
            e2 = [0; 1];
            power = @(i) [voltage'*i; ...
                voltage(2)*i(1)-voltage(1)*i(2)];
            finiteDifference = [ ...
                (power(current+h*e1)-power(current-h*e1))/(2*h), ...
                (power(current+h*e2)-power(current-h*e2))/(2*h)];

            testCase.verifyEqual(result.E, finiteDifference, AbsTol=1e-9);
        end

        function testPowerVoltageJacobianByFiniteDifference(testCase)
            operatingPoint = struct('vd', 0.8, 'vq', 0.3, ...
                'id', 0.4, 'iq', -0.2);
            result = buildPowerPolarLinearization(operatingPoint);
            h = 1e-6;
            voltage = [operatingPoint.vd; operatingPoint.vq];
            current = [operatingPoint.id; operatingPoint.iq];
            e1 = [1; 0];
            e2 = [0; 1];
            power = @(v) [v'*current; ...
                v(2)*current(1)-v(1)*current(2)];
            finiteDifference = [ ...
                (power(voltage+h*e1)-power(voltage-h*e1))/(2*h), ...
                (power(voltage+h*e2)-power(voltage-h*e2))/(2*h)];

            testCase.verifyEqual(result.C, finiteDifference, AbsTol=1e-9);
        end

        function testConverterAndNetworkInterconnectionIdentity(testCase)
            operatingPoint = struct('vd', 0.8, 'vq', 0.3, ...
                'id', 0.4, 'iq', -0.2);
            result = buildPowerPolarLinearization(operatingPoint);
            converterAdmittance = [1+0.2i, 0.3; -0.1i, 0.8];
            networkAdmittance = [2-0.1i, -0.4; 0.2i, 1.5];
            shapedConverter = ...
                (result.E*converterAdmittance+result.C)*result.F;
            shapedNetwork = ...
                (result.E*networkAdmittance-result.C)*result.F;

            testCase.verifyEqual(shapedConverter+shapedNetwork, ...
                result.E*(converterAdmittance+networkAdmittance)*result.F, ...
                AbsTol=1e-13);
        end

        function testZeroVoltageIsRejected(testCase)
            operatingPoint = struct('vd', 0, 'vq', 0, 'id', 1, 'iq', 0);

            testCase.verifyError( ...
                @() buildPowerPolarLinearization(operatingPoint), ...
                'gfm:buildPowerPolarLinearization:ZeroVoltage');
        end

        function testNonfiniteValueIsRejected(testCase)
            operatingPoint = struct('vd', NaN, 'vq', 0, 'id', 1, 'iq', 0);

            testCase.verifyError( ...
                @() buildPowerPolarLinearization(operatingPoint), ...
                'gfm:buildPowerPolarLinearization:InvalidField');
        end

        function testUnknownFieldIsRejected(testCase)
            operatingPoint = struct('vd', 1, 'vq', 0, ...
                'id', 1, 'iq', 0, 'angle', 0);

            testCase.verifyError( ...
                @() buildPowerPolarLinearization(operatingPoint), ...
                'gfm:buildPowerPolarLinearization:UnknownField');
        end
    end
end
