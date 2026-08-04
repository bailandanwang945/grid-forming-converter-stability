classdef evaluateMixedGainPhaseSamplesTest < matlab.unittest.TestCase
    %EVALUATEMIXEDGAINPHASESAMPLESTEST Sampled mixed-condition logic.

    methods (TestClassSetup)
        function addSourceFolder(testCase)
            projectRoot = fileparts(fileparts(mfilename('fullpath')));
            testCase.applyFixture(matlab.unittest.fixtures.PathFixture( ...
                fullfile(projectRoot, 'src')));
        end
    end

    methods (Test, TestTags = {'Unit'})
        function testGainPassCoversNonsectorialConverter(testCase)
            converters = {0.1*diag([1, -1])};

            result = testCase.evaluate(converters, eye(2));

            testCase.verifyEqual(result.gainStatus, "pass");
            testCase.verifyEqual(result.sampleCoverage, "gain-pass");
            testCase.verifyEqual(result.sampledBandStatus, ...
                "gain-covered-on-grid");
        end

        function testPhasePassCoversGainFailure(testCase)
            converters = {2*exp(0.2i)*eye(2)};

            result = testCase.evaluate(converters, eye(2));

            testCase.verifyEqual(result.gainStatus, "fail");
            testCase.verifyEqual(result.phaseStatus, "pass");
            testCase.verifyEqual(result.sampleCoverage, "phase-pass");
        end

        function testBothConditionsPass(testCase)
            result = testCase.evaluate({0.5*eye(2)}, eye(2));

            testCase.verifyEqual(result.sampleCoverage, "both-pass");
        end

        function testClearFailureDoesNotClaimInstability(testCase)
            phases = [0, 2*pi/3, -2*pi/3];
            converter = 2*diag(exp(1i*phases));

            result = testCase.evaluate({converter}, eye(3));

            testCase.verifyEqual(result.sampleCoverage, "uncovered");
            testCase.verifyEqual(result.sampledBandStatus, ...
                "not-covered-on-grid-under-phase-branch-assumption");
            testCase.verifyEqual(result.theoremStatus, ...
                "not-evaluated-by-sampled-api");
            testCase.verifySubstring(result.interpretationBoundary, ...
                "does not mean");
        end

        function testCrossConverterPhaseSpreadIsEnforced(testCase)
            converters = {2*exp(0.6i*pi), 2*exp(-0.6i*pi)};

            result = testCase.evaluate(converters, eye(2));

            testCase.verifyLessThan(result.converterPhaseSpreadMargin, 0);
            testCase.verifyEqual(result.phaseStatus, "fail");
            testCase.verifyEqual(result.sampleCoverage, "uncovered");
            testCase.verifyTrue(any(result.reasonCodes{1} == ...
                "converter-phase-spread-overlap"));
        end

        function testFiniteGridPassDoesNotCompleteTheorem(testCase)
            preconditions = testCase.completePreconditions();
            preconditions.fullFrequencyCoverage = false;

            result = testCase.evaluate( ...
                {0.5*eye(2)}, eye(2), preconditions);

            testCase.verifyEqual(result.sampledBandStatus, ...
                "gain-covered-on-grid");
            testCase.verifyEqual(result.theoremStatus, ...
                "not-evaluated-by-sampled-api");
        end

        function testCompleteDeclaredPreconditionsStillDoNotEvaluateTheorem(testCase)
            result = testCase.evaluate({0.5*eye(2)}, eye(2), ...
                testCase.completePreconditions());

            testCase.verifyEqual(result.theoremStatus, ...
                "not-evaluated-by-sampled-api");
            testCase.verifyEqual(result.preconditionDeclarationStatus, ...
                "complete");
            testCase.verifyTrue(result.declaredPreconditionsSatisfied);
        end

        function testIllConditionedNetworkMakesUncoveredPhasePending(testCase)
            converters = {2*eye(2)};
            network = diag([1, 1e-14]);

            result = testCase.evaluate(converters, network);

            testCase.verifyEqual(result.gainStatus, "fail");
            testCase.verifyEqual(result.phaseStatus, "indeterminate");
            testCase.verifyEqual(result.sampleCoverage, "indeterminate");
        end

        function testMultipleFrequencySamplesRetainIndividualCoverage(testCase)
            converters = {cat(3, 0.5*eye(2), 2*exp(0.2i)*eye(2))};
            network = cat(3, eye(2), eye(2));

            result = evaluateMixedGainPhaseSamples( ...
                converters, network, [1, 2], testCase.conventions(), ...
                testCase.incompletePreconditions(), ...
                testCase.seedOptions(1));

            testCase.verifyEqual(result.sampleCoverage, ...
                ["both-pass", "phase-pass"]);
            testCase.verifyEqual(result.sampledBandStatus, ...
                "covered-on-grid-under-phase-branch-assumption");
        end

        function testMissingPhaseSeedsLeavesPhaseIndeterminate(testCase)
            result = evaluateMixedGainPhaseSamples({2*eye(2)}, eye(2), ...
                1, testCase.conventions(), ...
                testCase.incompletePreconditions(), struct());

            testCase.verifyEqual(result.phaseStatus, "indeterminate");
            testCase.verifyEqual(result.phaseBranchReasonCodes(:, 1), ...
                ["phase-branch-unanchored"; ...
                 "phase-branch-unanchored"]);
        end

        function testContinuousBranchRejectsThirdOrderFalseConfirmation(testCase)
            omega = [0, 1, 2, 4, 8, 100];
            converter = reshape(382./(1+1i*omega).^3, 1, 1, []);
            network = ones(1, 1, numel(omega));

            result = evaluateMixedGainPhaseSamples({converter}, network, ...
                omega/(2*pi), testCase.conventions(), ...
                testCase.incompletePreconditions(), ...
                testCase.seedOptions(1));

            testCase.verifyEqual(result.sampledBandStatus, ...
                "not-covered-on-grid-under-phase-branch-assumption");
            testCase.verifyLessThan(result.converterLowerPhase(1, end), ...
                -1.4*pi);
            testCase.verifyTrue(any(result.sampleCoverage == "uncovered"));
            closedLoopPoles = roots([1, 3, 3, 383]);
            testCase.verifyGreaterThan(max(real(closedLoopPoles)), 0);
        end

        function testMultiplePhaseReasonsRemainAColumn(testCase)
            converters = {2*exp(1i*deg2rad(170)), ...
                2*exp(-1i*deg2rad(170))};
            options = struct('PhaseCenterSeeds', struct( ...
                'converterCenters', deg2rad([170; -170]), ...
                'networkInverseCenter', pi));

            result = evaluateMixedGainPhaseSamples(converters, -eye(2), ...
                1, testCase.conventions(), ...
                testCase.incompletePreconditions(), options);

            testCase.verifyEqual(size(result.reasonCodes{1}, 2), 1);
            testCase.verifyGreaterThanOrEqual(numel(result.reasonCodes{1}), 2);
        end

        function testWholeTurnAliasingIsOnlyConditionalScreening(testCase)
            omega = [0, 10];
            gain = 2*(1+omega(end)^2)^2;
            converter = reshape(gain./(1+1i*omega).^4, 1, 1, []);
            network = ones(1, 1, numel(omega));

            result = evaluateMixedGainPhaseSamples({converter}, network, ...
                omega/(2*pi), testCase.conventions(), ...
                testCase.incompletePreconditions(), ...
                testCase.seedOptions(1));

            testCase.verifyEqual(result.sampledBandStatus, ...
                "covered-on-grid-under-phase-branch-assumption");
            testCase.verifyEqual(result.phaseBranchAssumptionStatus, ...
                "user-seeded-nearest-neighbor-without-inter-sample-proof");
            testCase.verifyNotEqual(result.sampledBandStatus, ...
                "confirmed-on-grid");
            closedLoopPoles = roots([1, 4, 6, 4, 1+gain]);
            testCase.verifyGreaterThan(max(real(closedLoopPoles)), 0);
        end

        function testUnsupportedConventionIsRejected(testCase)
            conventions = testCase.conventions();
            conventions.currentDirection = "network-to-converter";

            testCase.verifyError(@() evaluateMixedGainPhaseSamples( ...
                {eye(2)}, eye(2), 1, conventions, ...
                testCase.incompletePreconditions(), ...
                testCase.seedOptions(1)), ...
                'gfm:evaluateMixedGainPhaseSamples:InvalidConvention');
        end

        function testAuthorFrameRequiresLoadConvention(testCase)
            conventions = testCase.conventions();
            conventions.frameConventionId = ...
                "cifelli-anta-author-global-synchronous-dq-v1";
            options = testCase.seedOptions(1);

            testCase.verifyError(@() evaluateMixedGainPhaseSamples( ...
                {eye(2)}, eye(2), 1, conventions, ...
                testCase.incompletePreconditions(), options), ...
                'gfm:evaluateMixedGainPhaseSamples:InvalidConvention');

            conventions.currentDirection = "network-to-converter";
            conventions.powerDirection = "load-positive";
            result = evaluateMixedGainPhaseSamples( ...
                {eye(2)}, eye(2), 1, conventions, ...
                testCase.incompletePreconditions(), options);
            testCase.verifyEqual(result.sampledBandStatus, ...
                "covered-on-grid-under-phase-branch-assumption");
        end
    end

    methods (Access=private)
        function result = evaluate(testCase, converters, network, preconditions)
            if nargin < 4
                preconditions = testCase.incompletePreconditions();
            end
            result = evaluateMixedGainPhaseSamples(converters, network, 1, ...
                testCase.conventions(), preconditions, ...
                testCase.seedOptions(numel(converters)));
        end

        function value = conventions(~)
            value = struct( ...
                'frameConventionId', ...
                    "analytic-test-global-synchronous-dq-v1", ...
                'currentDirection', "converter-to-network", ...
                'powerDirection', "injection-positive", ...
                'sBase', 1, ...
                'vBase', 1, ...
                'fBase', 50, ...
                'matrixType', "admittance", ...
                'globalFrameId', "test-global-dq");
        end

        function value = seedOptions(~, converterCount)
            value = struct('PhaseCenterSeeds', struct( ...
                'converterCenters', zeros(converterCount, 1), ...
                'networkInverseCenter', 0));
        end

        function value = incompletePreconditions(testCase)
            value = testCase.completePreconditions();
            value.endpointsCovered = false;
            value.fullFrequencyCoverage = false;
        end

        function value = completePreconditions(~)
            value = struct( ...
                'openLoopStable', true, ...
                'realRationalProper', true, ...
                'transformationWellDefined', true, ...
                'networkInverseStable', true, ...
                'noRhpCancellation', true, ...
                'endpointsCovered', true, ...
                'fullFrequencyCoverage', true);
        end
    end
end
