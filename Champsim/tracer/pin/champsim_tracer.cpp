/*
 *    Copyright 2023 The ChampSim Contributors
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/*! @file
 *  This is an example of the PIN tool that demonstrates some basic PIN APIs
 *  and could serve as the starting point for developing your first PIN tool
 */

#include <atomic>
#include <fstream>
#include <iostream>
#include <stdlib.h>
#include <string.h>
#include <string>
#include <sys/prctl.h>
#include <sys/syscall.h>

#include "../../inc/trace_instruction.h"
#include "pin.H"

using trace_instr_format_t = input_instr;

/* ================================================================== */
// Global variables
/* ================================================================== */

static std::atomic<UINT64> skippedInstrCount(0);
static std::atomic<UINT64> tracedInstructions(0);
static std::atomic<UINT64> tracedCumulativeInstructions(0);
static std::atomic<bool> tracingActive(false);
static std::atomic<bool> foundStartSymbol(false);
static std::atomic<bool> foundStopSymbol(false);
static std::atomic<bool> mainImageLoaded(false);
static std::atomic<THREADID> traceThreadId(static_cast<THREADID>(-1));

std::ofstream outfile;

trace_instr_format_t curr_instr;

/* ===================================================================== */
// Command line switches
/* ===================================================================== */
KNOB<std::string> KnobOutputFile(KNOB_MODE_WRITEONCE, "pintool", "o", "champsim.trace", "specify file name for Champsim tracer output");

KNOB<UINT64> KnobSkipInstructions(KNOB_MODE_WRITEONCE, "pintool", "s", "0", "How many instructions to skip before tracing begins");

KNOB<UINT64> KnobTraceInstructions(KNOB_MODE_WRITEONCE, "pintool", "t", "1000000", "How many instructions to trace");

KNOB<std::string> KnobStartSymbol(KNOB_MODE_WRITEONCE, "pintool", "start_symbol", "",
                                  "Symbol name to start tracing (e.g., 'main' or '_Z4testv'). If specified `-s` argument is ignored.");

KNOB<std::string> KnobStopSymbol(KNOB_MODE_WRITEONCE, "pintool", "stop_symbol", "", "Symbol name to stop tracing (optional)");

KNOB<std::string> KnobThreadName(KNOB_MODE_WRITEONCE, "pintool", "thread_name", "", "Only trace the native thread with this name");

/* ===================================================================== */
// Utilities
/* ===================================================================== */

/*!
 *  Print out help message.
 */
INT32 Usage()
{
  std::cerr << "This tool creates a register and memory access trace" << std::endl
            << "Specify the output trace file with -o" << std::endl
            << "Specify the number of instructions to skip before tracing with -s" << std::endl
            << "Specify the number of instructions to trace with -t" << std::endl
            << std::endl;

  std::cerr << KNOB_BASE::StringKnobSummary() << std::endl;

  return -1;
}

/* ===================================================================== */
// Analysis routines
/* ===================================================================== */

bool IsTraceThread(THREADID tid) { return traceThreadId.load() == tid; }

VOID ThreadStart(THREADID tid, CONTEXT* ctxt, INT32 flags, VOID* v)
{
  if (!KnobThreadName.Value().empty())
    return;
  auto unset = static_cast<THREADID>(-1);
  traceThreadId.compare_exchange_strong(unset, tid);
}

VOID ObserveThreadName(THREADID tid, ADDRINT nameAddress)
{
  if (KnobThreadName.Value().empty())
    return;

  char name[16] = {};
  PIN_SafeCopy(name, reinterpret_cast<const VOID*>(nameAddress), sizeof(name) - 1);
  if (KnobThreadName.Value() == name) {
    auto unset = static_cast<THREADID>(-1);
    if (traceThreadId.compare_exchange_strong(unset, tid))
      std::cout << "[PIN] Selected thread '" << name << "' (thread " << tid << ")" << std::endl;
  }
}

VOID SyscallEntry(THREADID tid, CONTEXT* ctxt, SYSCALL_STANDARD standard, VOID* v)
{
  if (KnobThreadName.Value().empty())
    return;

  if (PIN_GetSyscallNumber(ctxt, standard) == SYS_prctl &&
      PIN_GetSyscallArgument(ctxt, standard, 0) == PR_SET_NAME) {
    ObserveThreadName(tid, PIN_GetSyscallArgument(ctxt, standard, 1));
  }
}

void ResetCurrentInstruction(THREADID tid, VOID* ip)
{
  if (!IsTraceThread(tid))
    return;
  curr_instr = {};
  curr_instr.ip = (unsigned long long int)ip;
}

BOOL ShouldWrite(THREADID tid)
{
  if (!IsTraceThread(tid))
    return false;

  // Enable tracing when skip limit reached if not symbol-based tracing.
  // If using symbol-based tracing, `tracingActive` is set at the symbol instead.
  if (KnobStartSymbol.Value().empty() && skippedInstrCount > KnobSkipInstructions.Value()) {
    tracingActive = true;
  }
  if (tracingActive) {
    ++tracedInstructions;
    ++tracedCumulativeInstructions;
  } else {
    ++skippedInstrCount;
    return false;
  }
  if (tracedCumulativeInstructions > KnobTraceInstructions.Value()) {
    tracingActive = false;
    std::cout << "Reached instruction limit: " << KnobTraceInstructions.Value() << ". Stopping trace." << std::endl;
    // Note we don't use `PIN_Detach()` because that would stop instrumentation, but let the process continue, and there's no reason to do that.
    // Stop the application with code 0.
    PIN_ExitApplication(0);
    return false; // unreachable
  }
  return true;
}

void WriteCurrentInstruction(THREADID tid)
{
  if (!IsTraceThread(tid))
    return;
  typename decltype(outfile)::char_type buf[sizeof(trace_instr_format_t)];
  std::memcpy(buf, &curr_instr, sizeof(trace_instr_format_t));
  outfile.write(buf, sizeof(trace_instr_format_t));
}

void BranchOrNot(THREADID tid, UINT32 taken)
{
  if (!IsTraceThread(tid))
    return;
  curr_instr.is_branch = 1;
  curr_instr.branch_taken = taken;
}

UINT32 MapRegister(REG reg)
{
  if (reg == REG_STACK_PTR)
    return champsim::REG_STACK_POINTER;
  if (reg == REG_GFLAGS)
    return champsim::REG_FLAGS;
  if (reg == REG_INST_PTR)
    return champsim::REG_INSTRUCTION_POINTER;

  auto mapped = static_cast<UINT32>(reg);
  if (mapped == champsim::REG_STACK_POINTER || mapped == champsim::REG_FLAGS || mapped == champsim::REG_INSTRUCTION_POINTER)
    mapped += 32;
  return mapped;
}

template <typename T>
void WriteToSet(T* begin, T* end, UINT32 r);

void WriteBranchRegisters(THREADID tid, BOOL is_call, BOOL is_return, BOOL is_indirect, BOOL has_fall_through)
{
  if (!IsTraceThread(tid))
    return;

  if (is_return) {
    WriteToSet<unsigned char>(curr_instr.source_registers, curr_instr.source_registers + NUM_INSTR_SOURCES, champsim::REG_STACK_POINTER);
    WriteToSet<unsigned char>(curr_instr.destination_registers, curr_instr.destination_registers + NUM_INSTR_DESTINATIONS, champsim::REG_STACK_POINTER);
    WriteToSet<unsigned char>(curr_instr.destination_registers, curr_instr.destination_registers + NUM_INSTR_DESTINATIONS, champsim::REG_INSTRUCTION_POINTER);
  } else if (is_call) {
    WriteToSet<unsigned char>(curr_instr.source_registers, curr_instr.source_registers + NUM_INSTR_SOURCES, champsim::REG_STACK_POINTER);
    WriteToSet<unsigned char>(curr_instr.source_registers, curr_instr.source_registers + NUM_INSTR_SOURCES, champsim::REG_INSTRUCTION_POINTER);
    WriteToSet<unsigned char>(curr_instr.destination_registers, curr_instr.destination_registers + NUM_INSTR_DESTINATIONS, champsim::REG_STACK_POINTER);
    WriteToSet<unsigned char>(curr_instr.destination_registers, curr_instr.destination_registers + NUM_INSTR_DESTINATIONS, champsim::REG_INSTRUCTION_POINTER);
    if (is_indirect)
      WriteToSet<unsigned char>(curr_instr.source_registers, curr_instr.source_registers + NUM_INSTR_SOURCES, 0);
  } else {
    WriteToSet<unsigned char>(curr_instr.destination_registers, curr_instr.destination_registers + NUM_INSTR_DESTINATIONS, champsim::REG_INSTRUCTION_POINTER);
    if (has_fall_through) {
      WriteToSet<unsigned char>(curr_instr.source_registers, curr_instr.source_registers + NUM_INSTR_SOURCES, champsim::REG_INSTRUCTION_POINTER);
      WriteToSet<unsigned char>(curr_instr.source_registers, curr_instr.source_registers + NUM_INSTR_SOURCES, champsim::REG_FLAGS);
    } else if (is_indirect) {
      WriteToSet<unsigned char>(curr_instr.source_registers, curr_instr.source_registers + NUM_INSTR_SOURCES, 0);
    }
  }
}

void WriteRegister(THREADID tid, BOOL is_read, UINT32 regNum)
{
  if (!IsTraceThread(tid))
    return;
  if (is_read)
    WriteToSet<unsigned char>(curr_instr.source_registers, curr_instr.source_registers + NUM_INSTR_SOURCES, regNum);
  else
    WriteToSet<unsigned char>(curr_instr.destination_registers, curr_instr.destination_registers + NUM_INSTR_DESTINATIONS, regNum);
}

void WriteMemory(THREADID tid, BOOL is_read, ADDRINT address)
{
  if (!IsTraceThread(tid))
    return;
  if (is_read)
    WriteToSet<unsigned long long int>(curr_instr.source_memory, curr_instr.source_memory + NUM_INSTR_SOURCES, address);
  else
    WriteToSet<unsigned long long int>(curr_instr.destination_memory, curr_instr.destination_memory + NUM_INSTR_DESTINATIONS, address);
}

template <typename T>
void WriteToSet(T* begin, T* end, UINT32 r)
{
  auto set_end = std::find(begin, end, 0);
  auto found_reg = std::find(begin, set_end, r); // check to see if this register is already in the list
  *found_reg = r;
}

VOID StartTracing(VOID* ip)
{
  if (!tracingActive) {
    tracingActive = true;
    tracedInstructions = 0;
    std::cout << "[PIN] Started tracing at IP: 0x" << std::hex << ip << std::dec << std::endl;
  }
}

VOID StopTracing(VOID* ip)
{
  if (tracingActive) {
    tracingActive = false;
    std::cout << "[PIN] Stopped tracing at IP: 0x" << std::hex << ip << std::dec << " after " << tracedInstructions << " instructions" << std::endl;
  }
}

// Instrument image loads to find symbols
VOID ImageLoad(IMG img, VOID* v)
{
  RTN set_thread_name = RTN_FindByName(img, "pthread_setname_np");
  if (RTN_Valid(set_thread_name)) {
    RTN_Open(set_thread_name);
    RTN_InsertCall(set_thread_name, IPOINT_BEFORE, (AFUNPTR)ObserveThreadName, IARG_THREAD_ID, IARG_FUNCARG_ENTRYPOINT_VALUE, 1, IARG_END);
    RTN_Close(set_thread_name);
  }

  // Look for start symbol
  if (!KnobStartSymbol.Value().empty() && !foundStartSymbol.load()) {
    RTN rtn = RTN_FindByName(img, KnobStartSymbol.Value().c_str());

    if (RTN_Valid(rtn)) {
      foundStartSymbol.store(true);
      RTN_Open(rtn);
      // Insert call at function entry
      RTN_InsertCall(rtn, IPOINT_BEFORE, (AFUNPTR)StartTracing, IARG_INST_PTR, IARG_END);
      RTN_Close(rtn);

      std::cout << "Found start symbol '" << KnobStartSymbol.Value() << "' in image " << IMG_Name(img) << std::endl;
    }
  }

  // Look for stop symbol
  if (!KnobStopSymbol.Value().empty() && !foundStopSymbol.load()) {
    foundStopSymbol.store(true);
    RTN rtn = RTN_FindByName(img, KnobStopSymbol.Value().c_str());

    if (RTN_Valid(rtn)) {
      RTN_Open(rtn);
      // Insert call at function entry (or use IPOINT_AFTER for function exit)
      RTN_InsertCall(rtn, IPOINT_BEFORE, (AFUNPTR)StopTracing, IARG_INST_PTR, IARG_END);
      RTN_Close(rtn);

      std::cout << "Found stop symbol '" << KnobStopSymbol.Value() << "' in image " << IMG_Name(img) << std::endl;
    }
  }

  if (IMG_IsMainExecutable(img)) {
    bool exit = false;
    if (!KnobStartSymbol.Value().empty() && !foundStartSymbol.load()) {
      std::cerr << "[PIN] ERROR: Trace start symbol '" << KnobStartSymbol.Value() << "' not found!" << std::endl;
      exit = true;
    }
    if (!KnobStopSymbol.Value().empty() && !foundStopSymbol.load()) {
      std::cerr << "[PIN] ERROR: Trace stop symbol '" << KnobStopSymbol.Value() << "' not found!" << std::endl;
      exit = true;
    }
    if (exit) {
      PIN_ExitApplication(1);
    }
  }
}

/* ===================================================================== */
// Instrumentation callbacks
/* ===================================================================== */

// Is called for every instruction and instruments reads and writes
VOID Instruction(INS ins, VOID* v)
{
  // begin each instruction with this function
  INS_InsertCall(ins, IPOINT_BEFORE, (AFUNPTR)ResetCurrentInstruction, IARG_THREAD_ID, IARG_INST_PTR, IARG_END);

  // instrument branch instructions
  if (INS_IsBranch(ins)) {
    INS_InsertCall(ins, IPOINT_BEFORE, (AFUNPTR)BranchOrNot, IARG_THREAD_ID, IARG_BRANCH_TAKEN, IARG_END);
    INS_InsertCall(ins, IPOINT_BEFORE, (AFUNPTR)WriteBranchRegisters, IARG_THREAD_ID, IARG_BOOL, INS_IsCall(ins), IARG_BOOL, INS_IsRet(ins),
                   IARG_BOOL, INS_IsIndirectControlFlow(ins), IARG_BOOL, INS_HasFallThrough(ins), IARG_END);
  }

  // instrument register reads
  UINT32 readRegCount = INS_MaxNumRRegs(ins);
  for (UINT32 i = 0; i < readRegCount; i++) {
    UINT32 regNum = MapRegister(INS_RegR(ins, i));
    INS_InsertCall(ins, IPOINT_BEFORE, (AFUNPTR)WriteRegister, IARG_THREAD_ID, IARG_BOOL, TRUE, IARG_UINT32, regNum, IARG_END);
  }

  // instrument register writes
  UINT32 writeRegCount = INS_MaxNumWRegs(ins);
  for (UINT32 i = 0; i < writeRegCount; i++) {
    UINT32 regNum = MapRegister(INS_RegW(ins, i));
    INS_InsertCall(ins, IPOINT_BEFORE, (AFUNPTR)WriteRegister, IARG_THREAD_ID, IARG_BOOL, FALSE, IARG_UINT32, regNum, IARG_END);
  }

  // instrument memory reads and writes
  UINT32 memOperands = INS_MemoryOperandCount(ins);

  // Iterate over each memory operand of the instruction.
  for (UINT32 memOp = 0; memOp < memOperands; memOp++) {
    if (INS_MemoryOperandIsRead(ins, memOp))
      INS_InsertCall(ins, IPOINT_BEFORE, (AFUNPTR)WriteMemory, IARG_THREAD_ID, IARG_BOOL, TRUE, IARG_MEMORYOP_EA, memOp, IARG_END);
    if (INS_MemoryOperandIsWritten(ins, memOp))
      INS_InsertCall(ins, IPOINT_BEFORE, (AFUNPTR)WriteMemory, IARG_THREAD_ID, IARG_BOOL, FALSE, IARG_MEMORYOP_EA, memOp, IARG_END);
  }

  // finalize each instruction with this function
  INS_InsertIfCall(ins, IPOINT_BEFORE, (AFUNPTR)ShouldWrite, IARG_THREAD_ID, IARG_END);
  INS_InsertThenCall(ins, IPOINT_BEFORE, (AFUNPTR)WriteCurrentInstruction, IARG_THREAD_ID, IARG_END);
}

/*!
 * Print out analysis results.
 * This function is called when the application exits.
 * @param[in]   code            exit code of the application
 * @param[in]   v               value specified by the tool in the
 *                              PIN_AddFiniFunction function call
 */
VOID Fini(INT32 code, VOID* v) { outfile.close(); }

/*!
 * The main procedure of the tool.
 * This function is called when the application image is loaded but not yet started.
 * @param[in]   argc            total number of elements in the argv array
 * @param[in]   argv            array of command line arguments,
 *                              including pin -t <toolname> -- ...
 */
int main(int argc, char* argv[])
{
  PIN_InitSymbols();

  // Initialize PIN library. Print help message if -h(elp) is specified
  // in the command line or the command line is invalid
  if (PIN_Init(argc, argv))
    return Usage();

  outfile.open(KnobOutputFile.Value().c_str(), std::ios_base::binary | std::ios_base::trunc);
  if (!outfile) {
    std::cout << "Couldn't open output trace file. Exiting." << std::endl;
    exit(1);
  }

  // Register function to perform symbol lookup
  IMG_AddInstrumentFunction(ImageLoad, 0);

  PIN_AddThreadStartFunction(ThreadStart, 0);
  PIN_AddSyscallEntryFunction(SyscallEntry, 0);

  // Register function to be called to instrument instructions
  INS_AddInstrumentFunction(Instruction, 0);

  // Register function to be called when the application exits
  PIN_AddFiniFunction(Fini, 0);

  // Start the program, never returns
  PIN_StartProgram();

  return 0;
}
